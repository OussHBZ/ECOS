const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../static/js/kine-delivery.js'),'utf8');
function setup(storage) {
    const context={window:{},crypto:webcrypto,TextEncoder,sessionStorage:storage};
    vm.runInNewContext(source,context);return context.window.kardioxDelivery;
}
test('retry identity survives reload, separates sessions and does not store text',async()=>{
    const data=new Map();const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
    let delivery=setup(storage);const first=await delivery.key('/session/1','PRIVATE-TEXT');
    assert.equal(await delivery.key('/session/1','PRIVATE-TEXT'),first);
    delivery=setup(storage);assert.equal(await delivery.key('/session/1','PRIVATE-TEXT'),first);
    assert.notEqual(await delivery.key('/session/2','PRIVATE-TEXT'),first);
    assert.ok(!JSON.stringify([...data]).includes('PRIVATE-TEXT'));
    delivery.clear('/session/1');assert.notEqual(await delivery.key('/session/1','PRIVATE-TEXT'),first);
});
test('restricted session storage still retries in the same page',async()=>{
    const denied=()=>{throw Error('storage denied')};
    const delivery=setup({getItem:denied,setItem:denied,removeItem:denied});
    const key=await delivery.key('/message','hello');
    assert.equal(await delivery.key('/message','hello'),key);
    delivery.clear('/message');assert.notEqual(await delivery.key('/message','hello'),key);
});
