// PCM transport runs independently of the UI and servo control tick.
class CyoDuplex extends AudioWorkletProcessor {
  constructor() {
    super(); this.listen=false; this.capture=false; this.queue=[]; this.head=0; this.frames=0; this.phase=0;
    this.capPhase=0; this.previous=0; this.block=new Int16Array(320); this.pos=0;
    this.port.onmessage=({data})=>{
      if(data.listen!==undefined){this.listen=data.listen;if(!this.listen){this.queue=[];this.head=0;this.frames=0;this.phase=0;}}
      if(data.capture!==undefined){this.capture=data.capture;this.capPhase=0;this.pos=0;}
      if(data.pcm&&this.listen){const pcm=new Int16Array(data.pcm);this.queue.push(pcm);this.frames+=pcm.length/2;
        // Bound latency when a browser render was suspended.
        while(this.frames>3200&&this.queue.length>1){this.frames-=this.queue.shift().length/2-this.head;this.head=0;this.phase=0;}}
    };
  }
  process(inputs,outputs) {
    const out=outputs[0],input=inputs[0]; if(!out.length)return true;
    for(let i=0;i<out[0].length;i++){
      let l=0,r=0;
      if(this.listen&&this.queue.length){const q=this.queue[0],at=this.head*2;l=q[at]/32768;r=q[at+1]/32768;
        this.phase+=16000/sampleRate;
        while(this.phase>=1&&this.queue.length){this.phase--;this.head++;this.frames--;
          if(this.head*2>=this.queue[0].length){this.queue.shift();this.head=0;}}
      }
      out[0][i]=l;if(out[1])out[1][i]=r;
      if(this.capture&&input?.length){let x=input[0][i];if(input[1])x=(x+input[1][i])/2;
        // Fractional interpolation at exact 16 kHz, including non-48-kHz devices.
        while(this.capPhase<=1){const v=this.previous+(x-this.previous)*this.capPhase;
          this.block[this.pos++]=Math.round(Math.max(-1,Math.min(1,v))*32767);
          if(this.pos===320){this.port.postMessage({pcm:this.block.buffer},[this.block.buffer]);this.block=new Int16Array(320);this.pos=0;}
          this.capPhase+=sampleRate/16000;
        }
        this.capPhase--;this.previous=x;
      }
    }
    return true;
  }
}
registerProcessor('cyobot-duplex',CyoDuplex);
