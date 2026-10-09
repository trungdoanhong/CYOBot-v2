const $=s=>document.querySelector(s);
export function createEffectPanel({getState,isPreview,canControl,action,ledPanel,toast}){
  let selected='text',previewData=null,previewAt=0,ticket=0;
  const active=()=>isPreview()?!!previewData:!!getState().led_effect;
  document.querySelectorAll('[data-effect]').forEach(b=>b.onclick=()=>{selected=b.dataset.effect;update();});
  $('#effect-run').onclick=async()=>{
    if(active()){await stop();return;}
    if(!canControl())return;
    const color=$('#effect-color').value.match(/\w\w/g).map(c=>parseInt(c,16));
    const options={effect:selected,text:$('#effect-text').value.toUpperCase(),color,brightness:+$('#effect-brightness').value,speed:+$('#effect-speed').value};
    const current=++ticket;
    try{if(isPreview()){
      const response=await fetch('/api/led-preview?'+new URLSearchParams({...options,color:color.join(',')}));
      const data=await response.json();if(!response.ok)throw Error(data.error);
      if(current===ticket&&isPreview()){previewData=data;previewAt=performance.now();}
    }else await action('led_effect',options);}catch(e){toast(e.message,true);}update();
  };
  async function stop(){ticket++;previewData=null;if(!isPreview()&&getState().led_effect)await action('led_effect_stop');update();}
  function update(){const on=active();
    document.querySelectorAll('[data-effect]').forEach(b=>{b.classList.toggle('active',b.dataset.effect===selected);b.setAttribute('aria-pressed',String(b.dataset.effect===selected));});
    $('#effect-text-row').hidden=selected!=='text';
    $('#effect-run').disabled=!canControl()||(!isPreview()&&!getState().leds_supported);
    $('#effect-run').textContent=on?'Stop effect':isPreview()?'Preview effect':'Play effect';
    $('#effect-run').setAttribute('aria-label',$('#effect-run').textContent);
    $('#effect-status').textContent=on?(isPreview()?'Preview · PC only':getState().led_effect+' · live'):'Matrix + ring';
  }
  const timer=setInterval(()=>{if(previewData&&isPreview()&&!document.hidden){const i=Math.floor((performance.now()-previewAt)/(previewData.interval*1000))%previewData.frames.length;ledPanel.showPreview(previewData.frames[i]);}update();},80);
  // Manual paint and effects share one output. A manual frame replaces an effect.
  document.querySelectorAll('#led-matrix,#led-ring,#led-fill,#led-clear,[data-led-preset],#led-brightness').forEach(el=>{
    for(const event of ['pointerdown','click','input'])el.addEventListener(event,()=>{ticket++;previewData=null;});
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  window.addEventListener('pagehide',()=>clearInterval(timer));
  return {update,stopPreview(){ticket++;previewData=null;},stop};
}
