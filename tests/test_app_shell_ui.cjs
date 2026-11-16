const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../static/js/app-shell.js'),'utf8');

function setup(small = true) {
  let document, mutation;
  function element() {
    const classes = new Set();
    return {attrs:{},listeners:{},dataset:{},tabIndex:0,isConnected:true,inert:false,
      classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){on?classes.add(x):classes.delete(x);}},
      setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},removeAttribute(k){delete this.attrs[k];},hasAttribute(k){return k in this.attrs;},
      addEventListener(k,cb){this.listeners[k]=cb;},getClientRects(){return [{}];},closest(){return null;},
      focus(){document.activeElement=this;},querySelector(){return null;},querySelectorAll(){return [];},contains(el){return this===el;}
    };
  }
  const sidebar=element(),workspace=element(),trigger=element(),close=element(),last=element(),backdrop=element(),body=element();
  sidebar.querySelector=()=>close;
  sidebar.querySelectorAll=selector=>selector.startsWith('a[href]')?[close,last]:[];
  sidebar.contains=el=>[sidebar,close,last].includes(el);
  const media={matches:small,addEventListener(k,cb){this.change=cb;}};
  document={body,activeElement:trigger,listeners:{},
    querySelector:s=>({'.app-sidebar':sidebar,'.app-workspace':workspace,'[data-menu-open]':trigger,'[data-menu-backdrop]':backdrop,'[data-menu-close]':close}[s]||null),
    modals:[],querySelectorAll(selector){return selector === '.modal,#zoom-image-viewer,dialog.app-dialog' ? this.modals : [];}, addEventListener(k,cb){this.listeners[k]=cb;}
  };
  const confirmations=[];
  const browserWindow={matchMedia:()=>media,addEventListener(){},confirm(message){confirmations.push(message);return false;}};
  vm.runInNewContext(source,{document,window:browserWindow,location:{pathname:'/',hash:''},
    MutationObserver:class{constructor(cb){mutation=cb;}observe(){}},requestAnimationFrame:cb=>cb(),getComputedStyle:()=>({display:'block'})});
  return {document,sidebar,workspace,trigger,close,last,backdrop,body,media,mutation,element,confirmations,browserWindow};
}

test('mobile Menu opens an accessible navigation, Fermer restores trigger focus',()=>{
  const ui=setup();
  assert.equal(ui.sidebar.inert,true);
  ui.trigger.listeners.click();
  assert.equal(ui.trigger.attrs['aria-expanded'],'true');
  assert.equal(ui.workspace.inert,true);
  assert.equal(ui.sidebar.inert,false);
  assert.equal(ui.document.activeElement,ui.close);
  ui.close.listeners.click();
  assert.equal(ui.trigger.attrs['aria-expanded'],'false');
  assert.equal(ui.workspace.inert,false);
  assert.equal(ui.document.activeElement,ui.trigger);
});

test('mobile navigation traps Tab in both directions and Escape restores focus',()=>{
  const ui=setup();ui.trigger.listeners.click();
  let prevented=0;
  ui.last.focus();
  ui.document.listeners.keydown({key:'Tab',shiftKey:false,preventDefault(){prevented++;}});
  assert.equal(ui.document.activeElement,ui.close);
  ui.document.listeners.keydown({key:'Tab',shiftKey:true,preventDefault(){prevented++;}});
  assert.equal(ui.document.activeElement,ui.last);
  ui.document.listeners.keydown({key:'Escape',preventDefault(){prevented++;}});
  assert.equal(ui.document.activeElement,ui.trigger);
  assert.equal(prevented,3);
});

test('desktop resizing clears mobile modal state and keeps sidebar available',()=>{
  const ui=setup();ui.trigger.listeners.click();
  ui.media.matches=false;ui.media.change();
  assert.equal(ui.sidebar.inert,false);
  assert.equal(ui.workspace.inert,false);
  assert.equal(ui.backdrop.hidden,true);
  assert.equal(ui.body.classList.contains('menu-open'),false);
});

test('backdrop dismisses mobile navigation without losing trigger focus',()=>{
  const ui=setup();ui.trigger.listeners.click();ui.backdrop.listeners.click();
  assert.equal(ui.document.activeElement,ui.trigger);
  assert.equal(ui.sidebar.inert,true);
});

test('dynamic dialogs receive focus, trap Tab and restore focus through their existing close action',()=>{
  const ui=setup(false),modal=ui.element(),close=ui.element(),field=ui.element();
  modal.querySelector=selector=>selector === 'h1,h2,h3' ? {textContent:'Modifier le compte'} : close;
  modal.querySelectorAll=()=>[close,field];
  modal.contains=el=>[modal,close,field].includes(el);
  close.click=()=>{modal.classList.add('hidden');ui.mutation([{type:'childList'}]);};
  ui.document.modals=[modal];ui.mutation([{type:'childList'}]);
  assert.equal(modal.attrs.role,'dialog');
  assert.equal(modal.attrs['aria-modal'],'true');
  assert.equal(ui.body.classList.contains('dialog-open'),true);
  assert.equal(ui.document.activeElement,close);
  field.focus();
  ui.document.listeners.keydown({key:'Tab',preventDefault(){}});
  assert.equal(ui.document.activeElement,close);
  ui.document.listeners.keydown({key:'Escape',preventDefault(){}});
  assert.equal(ui.document.activeElement,ui.trigger);
  assert.equal(modal.attrs['aria-modal'],undefined);
  assert.equal(ui.body.classList.contains('dialog-open'),false);
});

test('dirty dialogs guard close buttons and backdrop without interfering with submit',()=>{
  const ui=setup(false),modal=ui.element(),field=ui.element(),close=ui.element();
  modal.querySelector=()=>close; modal.querySelectorAll=()=>[close,field];
  modal.contains=el=>[modal,close,field].includes(el);
  field.closest=()=>modal;
  close.textContent='Fermer';
  close.closest=selector=>selector.startsWith('.modal')?modal:close;
  ui.document.modals=[modal];ui.mutation([{type:'childList'}]);
  ui.document.listeners.input({target:field});
  let prevented=0,stopped=0;
  ui.document.listeners.click({target:close,preventDefault(){prevented++;},stopImmediatePropagation(){stopped++;}});
  assert.equal(ui.confirmations.length,1);assert.equal(prevented,1);assert.equal(stopped,1);
  assert.equal(ui.body.classList.contains('dialog-open'),true);
  const submit=ui.element();submit.textContent='Enregistrer';
  submit.closest=selector=>selector.startsWith('.modal')?modal:selector==='button,span,a'?submit:null;
  ui.document.listeners.click({target:submit,preventDefault(){prevented++;},stopImmediatePropagation(){stopped++;}});
  assert.equal(ui.confirmations.length,1);assert.equal(prevented,1);
  ui.browserWindow.confirm=()=>true;
  ui.document.listeners.click({target:close,preventDefault(){prevented++;},stopImmediatePropagation(){stopped++;}});
  assert.equal(prevented,1);
});
