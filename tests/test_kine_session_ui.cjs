// Execute the shipped UI handlers with small DOM doubles; no browser dependency.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../static/js', name), 'utf8');

test('record toggles twice with ARIA updates while the conversation and draft stay mounted', () => {
    let toggle;
    const attrs = {'aria-expanded':'true'};
    const button = {addEventListener(name, cb) {toggle=cb;}, getAttribute(name) {return attrs[name];}, setAttribute(name, value) {attrs[name]=value;}};
    const sidebar = {hidden:false};
    const layout = {classList:{toggle(name, value) {this[name]=value;}}};
    const draft = {value:'Question non envoyée'};
    const form = {elements:{message:draft}, addEventListener(){}};
    const messages = {children:[{textContent:'Historique conservé'}]};
    const root = {dataset:{}, querySelector(selector) {
        return {'[data-record-toggle]':button, '[data-record-sidebar]':sidebar, '.kine-chat-layout':layout,
            '[data-chat-messages]':messages,'[data-chat-form]':form}[selector] || null;
    }};
    vm.runInNewContext(source('kine-chat.js'), {document:{querySelector(){return root;}}, window:{addEventListener(){}}});
    toggle();
    assert.equal(sidebar.hidden,true); assert.equal(attrs['aria-expanded'],'false');
    assert.equal(layout.classList['record-collapsed'],true);
    toggle();
    assert.equal(sidebar.hidden,false); assert.equal(attrs['aria-expanded'],'true');
    assert.equal(draft.value,'Question non envoyée'); assert.equal(messages.children[0].textContent,'Historique conservé');
    assert.equal(root.querySelector('[data-chat-form]'),form);
});

test('exam topic selection follows the server, including a return to history, and never paints completion', async () => {
    let ready, click;
    let requested;
    const steps = [1,2,3].map(number => ({dataset:{phase:String(number)},
        classList:{toggle(){}, remove(name) {assert.equal(name,'is-complete');}}, querySelector(){return null;}}));
    const root = {dataset:{mode:'exam', currentPhase:'3', progressUrl:'/progress'},
        querySelectorAll(){return steps;}, querySelector(){return null;},
        addEventListener(name, cb){click=cb;}, dispatchEvent(){}};
    vm.runInNewContext(source('kine-components.js'), {
        document:{addEventListener(name, cb){if(name==='DOMContentLoaded')ready=cb;},
            querySelector(){return null;}, querySelectorAll(selector){return selector==='[data-kine-tracker]'?[root]:[];}},
        window:{addEventListener(){}}, CustomEvent:class{}, console,
        secureFetch:async(url, options)=>{requested=JSON.parse(options.body); return {ok:true,json:async()=>({current_phase:1,phases:steps.map((s,i)=>({number:i+1,locked:false}))})};},
    });
    ready();
    click({target:{closest(){return {disabled:false,dataset:{phaseButton:'1'}};}}});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(requested.phase,1); assert.equal(root.dataset.currentPhase,'1');
});

test('teacher preview preserves a failed draft and creates a new session after reset', async () => {
    let submit, reset;
    let body;
    const input={value:'Question fictive'};
    const button={disabled:false};
    const form={elements:{message:input},addEventListener(name,cb){submit=cb;},querySelector(){return button;}};
    const messages={append(){},replaceChildren(){}};
    const root={dataset:{url:'/preview'},querySelector(selector){return {
        '[data-preview-form]':form,'[data-preview-messages]':messages,
        '[data-preview-reset]':{addEventListener(name,cb){reset=cb;}},'[data-preview-level]':{value:'master'},
    }[selector];}};
    let fail=true;
    vm.runInNewContext(source('kine-preview.js'),{
        document:{querySelector(){return root;},createElement(){return {};}},
        secureFetch:async(url,options)=>{body=JSON.parse(options.body);return {ok:!fail,json:async()=>fail?{error:'Indisponible'}:{preview_id:'preview-A',response:{content:'Fait'}}};},
    });
    await submit({preventDefault(){}}); assert.equal(input.value,'Question fictive'); assert.equal(button.disabled,false);
    fail=false; await submit({preventDefault(){}}); assert.equal(input.value,'');
    input.value='Suite'; await submit({preventDefault(){}}); assert.equal(body.preview_id,'preview-A');
    reset(); input.value='Nouveau'; await submit({preventDefault(){}}); assert.equal(body.preview_id,null);
});

test('effort UI sends test and moment IDs and renders a separate table for each test', async () => {
    const element = () => ({children:[],append(...nodes){this.children.push(...nodes);}});
    const body=element(); const selector=element(); const status={};
    let submit, sent;
    const root={dataset:{url:'/effort',eventUrl:'/event'},querySelector(selectorName){return {
        '[name="measurement"]':selector,'[data-effort-status]':status,'[data-effort-results]':body,
        'form':{addEventListener(name,cb){submit=cb;}}, '[name="observed_value"]':{value:''},
        '[data-effort-event-form]':{addEventListener(){}},
    }[selectorName];}};
    const context={window:{},crypto:require('node:crypto').webcrypto,TextEncoder,
        sessionStorage:{getItem(){return null;},setItem(){},removeItem(){}},
        document:{querySelector(selectorName){return selectorName==='[data-effort-panel]'?root:null;},createElement:element},
        secureFetch:async(url,options)=>{
            if(options?.body){sent=JSON.parse(options.body);return {ok:true,json:async()=>({measurement:{test_id:sent.test_id,test_name:sent.test_id,id:sent.measurement_id,name:'FC',moment:'initial',actor:'student',status:'value',value:71,unit:'bpm'}})};}
            return {ok:true,json:async()=>({tests:['walk','cycle'].map(id=>({id,name:id,measurements:[{id:'start',name:'FC',moment:'initial',actor:'student'}]})),measurements:[]})};
        },
    };
    vm.createContext(context);
    vm.runInContext(source('kine-delivery.js'),context);
    vm.runInContext(source('kine-effort.js'),context);
    await new Promise(resolve=>setImmediate(resolve));
    selector.value='walk/start';await submit({preventDefault(){},submitter:{dataset:{}}});
    assert.match(sent.request_id,/^[0-9a-f-]{36}$/);const firstKey=sent.request_id;
    assert.deepEqual(sent,{test_id:'walk',measurement_id:'start',request_id:firstKey});
    selector.value='cycle/start';await submit({preventDefault(){},submitter:{dataset:{}}});
    assert.notEqual(sent.request_id,firstKey);
    assert.deepEqual(sent,{test_id:'cycle',measurement_id:'start',request_id:sent.request_id});
    assert.equal(body.children.length,4); // heading + distinct table for each test
    assert.equal(body.children[0].textContent,'walk');assert.equal(body.children[2].textContent,'cycle');
    assert.notEqual(body.children[1],body.children[3]);
});

test('information editor saves level and disclosure conditions without rewriting clinical facts', async () => {
    const fields={};let save, sent;
    for(const key of ['status','item','label','value','mode','knowledge','terms','requires','licence','master','refresh','save']){
        fields[key]={value:'',selectedOptions:[],replaceChildren(){},append(){},addEventListener(name,cb){if(key==='save')save=cb;}};
    }
    const item={stable_id:'fact-1',label:'Information',path:'custom.symptom',value:'FAIT-CLINIQUE',access_mode:'question',
        patient_knows:true,level_rules:{},disclosure_conditions:{terms:['douleur']}};
    const root={dataset:{url:'/cases/7/information'},querySelector(selector){return fields[selector.match(/data-policy-(.+)\]/)[1]];}};
    vm.runInNewContext(source('kine-information-policy.js'),{
        document:{querySelector(){return root;},createElement(){return {};}},
        secureFetch:async(url,options)=>{
            if(options){sent={url,...options,body:JSON.parse(options.body)};return {ok:true,json:async()=>({...item,...sent.body})};}
            return {ok:true,json:async()=>({information:[item]})};
        },
    });
    await new Promise(resolve=>setImmediate(resolve));
    fields.mode.value='deepening';fields.licence.value='initial';fields.knowledge.value='false';
    fields.terms.value='douleur | précision';fields.requires.selectedOptions=[{value:'prerequisite'}];
    await save();
    assert.equal(sent.url,'/cases/7/information/fact-1');assert.equal(sent.method,'PUT');
    assert.equal(sent.body.patient_knows,false);assert.equal(sent.body.level_rules.licence.access_mode,'initial');
    assert.deepEqual(sent.body.disclosure_conditions.requires_information,['prerequisite']);
    assert.equal(Object.hasOwn(sent.body,'value'),false);
    assert.equal(fields.save.disabled,false);assert.match(fields.status.textContent,/enregistrée/);
});
