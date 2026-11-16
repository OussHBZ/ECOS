(function () {
    const form=document.querySelector('[data-observer-form]');
    if (!form) return;
    let pending=false;
    form.addEventListener('submit',async event=>{
        event.preventDefault(); if(pending)return;
        pending=true; const button=form.querySelector('button');button.disabled=true;
        const status=form.querySelector('[data-observer-status]');
        try{
            const data={...JSON.parse(form.elements.measurement.value),observed_value:form.elements.observed_value.value};
            data.request_id=await window.kardioxDelivery.key(form.dataset.url,JSON.stringify(data));
            const response=await secureFetch(form.dataset.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
            const result=await response.json();if(!response.ok)throw new Error(result.error || 'Observation indisponible.');
            window.kardioxDelivery.clear(form.dataset.url);
            status.textContent='Observation enregistrée.';form.elements.observed_value.value='';
        }catch(error){status.textContent=error.message;}
        finally{pending=false;button.disabled=false;}
    });
})();
