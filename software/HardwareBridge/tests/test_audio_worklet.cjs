const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('host/ui/audio-worklet.js','utf8');
for(const rate of [44100,48000]){
  let Processor;const sent=[];
  const sandbox={sampleRate:rate,AudioWorkletProcessor:class{constructor(){this.port={postMessage:msg=>sent.push(msg.pcm)}}},registerProcessor:(_,p)=>Processor=p};
  vm.runInNewContext(code,sandbox);const p=new Processor();p.port.onmessage({data:{capture:true}});
  let samples=0;while(samples<rate){const n=Math.min(128,rate-samples),input=new Float32Array(n).fill(.25);
    p.process([[input,input]],[[new Float32Array(n),new Float32Array(n)]]);samples+=n;}
  assert.equal(sent.length,50,'capture generates exactly 50 frames/s at '+rate);
  assert.equal(new Int16Array(sent[1])[0],8192);
  p.port.onmessage({data:{capture:false,listen:true}});
  const pcm=new Int16Array(640);for(let i=0;i<320;i++){pcm[2*i]=8192;pcm[2*i+1]=-8192;}
  for(let i=0;i<30;i++)p.port.onmessage({data:{pcm:pcm.buffer}});
  assert(p.frames<=3200,'playback backlog bounded to 200 ms');
  const left=new Float32Array(128),right=new Float32Array(128);p.process([],[[left,right]]);
  assert.equal(left[0],.25);assert.equal(right[0],-.25);
  p.port.onmessage({data:{listen:false}});p.process([],[[left,right]]);assert(left.every(v=>v===0));assert.equal(p.frames,0);
}
console.log('PASS PCM worklet: 44.1/48 kHz capture, stereo playback, bounded queue, stop');
