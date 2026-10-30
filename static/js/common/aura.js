// 光标光晕：跟随鼠标的一团光，带平滑跟随（缓动）。
//
// 纯装饰效果，不参与任何业务逻辑。
// 鼠标离开窗口时淡出，避免光晕停在边缘。

const aura = $("cursor-aura");
let mouseX = 0, mouseY = 0;
let auraX = 0, auraY = 0;

document.addEventListener("mousemove", (e) => {
  mouseX = e.clientX;
  mouseY = e.clientY;
  if (aura && aura.style.opacity === "0") aura.style.opacity = "1";
});

document.addEventListener("mouseleave", () => { if (aura) aura.style.opacity = "0"; });

function animateAura(){
  if (aura){
    // 0.15 是缓动系数：越小跟得越慢、越有拖尾感
    auraX += (mouseX - auraX) * 0.15;
    auraY += (mouseY - auraY) * 0.15;
    aura.style.transform = `translate(${auraX}px, ${auraY}px) translate(-50%, -50%)`;
  }
  requestAnimationFrame(animateAura);
}

animateAura();
