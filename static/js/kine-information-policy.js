(function () {
    const root=document.querySelector('[data-information-editor]');if(!root)return;
    const field=name=>root.querySelector(`[data-policy-${name}]`);
    const status=field('status');const select=field('item');let items=[],pending=false;
    function show(){
        const item=items.find(row=>row.stable_id===select.value);if(!item)return;
        field('label').value=item.label;field('value').textContent=JSON.stringify(item.value,null,2);
        field('mode').value=item.access_mode;
        field('knowledge').value=item.patient_knows===null?'':String(item.patient_knows);
        field('terms').value=(item.disclosure_conditions.terms||[]).join('|');
        ['licence','master'].forEach(level=>{field(level).value=item.level_rules[level]?.access_mode||'';});
        const requires=field('requires');requires.replaceChildren();
        items.filter(row=>row.stable_id!==item.stable_id && row.access_mode!=='evaluation_reserved').forEach(row=>{
            const option=document.createElement('option');option.value=row.stable_id;option.textContent=row.label;
            option.selected=(item.disclosure_conditions.requires_information||[]).includes(row.stable_id);requires.append(option);
        });
    }
    async function load(){
        try{
            const response=await secureFetch(root.dataset.url);const data=await response.json();
            if(!response.ok)throw new Error(data.error||'Informations indisponibles.');
            items=data.information;select.replaceChildren();
            items.forEach(item=>{const option=document.createElement('option');option.value=item.stable_id;option.textContent=`${item.label} · ${item.path}`;select.append(option);});
            if(items.length)select.value=items[0].stable_id;show();
        }catch(error){status.textContent=error.message;}
    }
    select.addEventListener('change',show);field('refresh').addEventListener('click',()=>{if(!pending)load();});
    field('save').addEventListener('click',async()=>{
        if(pending || !select.value)return;pending=true;field('save').disabled=true;
        try{
            const level_rules={};['licence','master'].forEach(level=>{if(field(level).value)level_rules[level]={access_mode:field(level).value};});
            const body={label:field('label').value,access_mode:field('mode').value,
                patient_knows:field('knowledge').value===''?null:field('knowledge').value==='true',level_rules,
                disclosure_conditions:{terms:field('terms').value.split('|').map(term=>term.trim()).filter(Boolean),
                    requires_information:Array.from(field('requires').selectedOptions).map(option=>option.value)}};
            const response=await secureFetch(`${root.dataset.url}/${encodeURIComponent(select.value)}`,{
                method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            const data=await response.json();if(!response.ok)throw new Error(data.error||'Règle refusée.');
            items=items.map(item=>item.stable_id===data.stable_id?data:item);status.textContent='Règle enregistrée dans le brouillon.';
        }catch(error){status.textContent=error.message;}
        finally{pending=false;field('save').disabled=false;}
    });
    load();
})();
