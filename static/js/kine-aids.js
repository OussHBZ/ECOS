(() => {
    const button=document.querySelector('[data-aids-url]');
    if(!button)return;
    button.addEventListener('click',async()=>{
        const target=document.querySelector('[data-aids-content]');
        try {
            const response=await fetch(button.dataset.aidsUrl,{headers:{Accept:'application/json'}});
            const data=await response.json();target.replaceChildren();
            if(!response.ok)throw new Error(data.error||'Aides indisponibles.');
            (data.aids.length?data.aids:[{text:'Aucun indice activé ou accessible pour le moment.'}]).forEach(row=>{const p=document.createElement('p');p.textContent=row.text;target.append(p);});
        } catch(error){target.textContent=error.message;}
    });
})();
