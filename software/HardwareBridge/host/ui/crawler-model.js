import * as THREE from 'three';
import URDFLoader from '/vendor/urdf/URDFLoader.js';

export const MODEL_SCALE = 20; // URDF metres to the Studio's display units.

// Reuse the assembled Blender/URDF robot, including its four-bar mimic joints.
export async function loadCrawler(parent, onProgress=()=>{}) {
  return new Promise((resolve, reject)=>{
    let robot, failed=false;
    const manager=new THREE.LoadingManager();
    manager.onProgress=(_,loaded,total)=>onProgress(Math.round(loaded/total*100));
    manager.onError=url=>{failed=true;reject(new Error(`Could not load model: ${url}`));};
    manager.onLoad=()=>{
      if(failed||!robot)return;
      const meshes=[],picks=[];
      robot.traverse(o=>{
        if(!o.isMesh)return;
        const original=o.material;
        o.material=new THREE.MeshStandardMaterial({color:original.color,opacity:original.opacity,transparent:original.transparent,side:original.side,roughness:.52,metalness:.08});
        o.castShadow=true;o.receiveShadow=true;meshes.push(o);
        let link=o.parent,visual=o.parent;
        while(link&&!link.isURDFLink)link=link.parent;
        while(visual&&!visual.isURDFVisual)visual=visual.parent;
        const leg=link?.name.match(/^leg([1-4])_(hip|lower|upper|foot)$/);
        const actuator=visual?.name.match(/^Actuator_([1-4])_(hip|foot)_/);
        if(leg)o.userData.joint=(+leg[1]-1)*2+(leg[2]==='hip'?0:1);
        else if(actuator)o.userData.joint=(+actuator[1]-1)*2+(actuator[2]==='hip'?0:1);
        if(o.userData.joint!==undefined)picks.push(o);
      });
      // Display every commanded angle. Keep source mechanical limits as metadata.
      // The visualizer does not enforce or simulate physical collision limits.
      Object.values(robot.joints).forEach(j=>j.ignoreLimits=true);
      robot.rotation.x=-Math.PI/2;
      robot.scale.setScalar(MODEL_SCALE);
      parent.add(robot);
      robot.updateMatrixWorld(true);
      const bounds=new THREE.Box3().setFromObject(robot);
      parent.position.y=-.045-bounds.min.y;
      const joints=[];
      for(let leg=1;leg<=4;leg++)for(const name of ['hip','foot']){
        const joint=robot.joints[`leg${leg}_${name}_servo`];
        joint.userData.joint=joints.length;joints.push(joint);
      }
      const displayAngles=Array(8).fill(0);
      const adapter={
        robot,picks,joints,meshCount:meshes.length,
        pose(angles,dt){
          const blend=1-Math.exp(-Math.min(dt,.1)*22);
          angles.forEach((angle,i)=>{
            displayAngles[i]+= (angle-displayAngles[i])*blend;
            robot.setJointValue(joints[i].name,THREE.MathUtils.degToRad(displayAngles[i]));
          });
        },
        highlight(index){meshes.forEach(m=>{const selected=m.userData.joint===index;m.material.emissive.setHex(selected?0x174b2a:0);m.material.emissiveIntensity=selected ? .24 : 0;});},
        diagnostics(){
          robot.updateMatrixWorld(true);
          const a=new THREE.Vector3(),b=new THREE.Vector3(),closure_mm=[];
          for(let leg=1;leg<=4;leg++){
            a.set(.032,0,0);robot.links[`leg${leg}_upper`].localToWorld(a);
            b.set(-.0212,0,.012);robot.links[`leg${leg}_hip`].localToWorld(b);
            closure_mm.push(a.distanceTo(b)/MODEL_SCALE*1000);
          }
          return {source:'cyobot-web/robot/crawler.urdf (2026-09-27)',meshes:meshes.length,angles_deg:joints.map(j=>THREE.MathUtils.radToDeg(j.jointValue[0])),closure_mm};
        }
      };
      resolve(adapter);
    };
    const loader=new URDFLoader(manager);loader.parseCollision=false;
    loader.load('/robot/crawler.urdf',r=>{robot=r;},undefined,reject);
  });
}
