const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../static/js/kine-chat.js'),'utf8');
test('network outage retains the draft and does not pause or abandon; reconnect uses the original attempt', async () => {
  const events={};const connection={textContent:''};const input={value:'Brouillon conservé',disabled:false};let reload=0;const requests=[];
  const root={dataset:{status:'in_progress',reconnectUrl:'/kine/simulation/7/reconnect'},
    querySelector:s=>s==='[data-connection-status]'?connection:null,querySelectorAll:()=>[input]};
  vm.runInNewContext(source,{document:{querySelector:()=>root}, window:{addEventListener:(key,fn)=>events[key]=fn,location:{reload:()=>reload++}},
    secureFetch:async (url,opts)=>{requests.push({url,opts});return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({status:'in_progress'})};}});
  events.offline();assert.equal(input.disabled,true);assert.equal(input.value,'Brouillon conservé');assert.equal(requests.length,0);
  assert.equal(root.dataset.status,'in_progress');assert.match(connection.textContent,/chrono/);
  await events.online();assert.equal(requests.length,1);assert.equal(requests[0].url,'/kine/simulation/7/reconnect');assert.equal(reload,0);assert.equal(input.disabled,false);assert.equal(input.value,'Brouillon conservé');
  root.dataset.status='completed';await events.online();assert.equal(requests.length,1);
});
