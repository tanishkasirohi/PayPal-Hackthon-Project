const API = '';
const state = { mode: 'individual', request: '', requirements: null, recommendations: [], selected: null, order: null, aiMode: 'demo parser', paypalReady: false };
const $ = (s) => document.querySelector(s);
const money = (value, currency='USD') => new Intl.NumberFormat('en-US',{style:'currency',currency,maximumFractionDigits:2}).format(Number(value));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, options={}) {
  const res = await fetch(API+path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  const data = await res.json().catch(()=>({detail:'The server returned an unreadable response.'}));
  if(!res.ok) throw new Error(data.detail || data.error?.message || 'Something went wrong. Please try again.');
  return data;
}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function init(){
  try{
    const h=await api('/api/health');
    const badge=$('#ai-badge'); badge.classList.add(h.ai_configured?'ready':'warn');
    badge.innerHTML=`<i></i> ${h.ai_configured?'AI connected':'Demo parser'} <span style="padding:0 4px;color:#d6dcd5">·</span> ${h.paypal_configured?'PayPal Sandbox ready':'PayPal setup needed'}`;
    if(!h.paypal_configured){$('.paypal-button span:last-child').innerHTML='Save approved purchase draft <b>→</b>';$('.secure-note').textContent='Add PayPal Sandbox credentials to enable checkout.';}
    if(h.paypal_configured && !window.paypal) loadPayPal(h);
  }catch(e){$('#ai-badge').classList.add('warn');$('#ai-badge').textContent='Backend not connected';}
  refreshOrdersCount();
  handlePayPalReturn();
}
function loadPayPal(health){
  if(!health.paypal_configured || !health.client_id) return;
  const script=document.createElement('script');
  script.src=`https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(health.client_id)}&currency=${encodeURIComponent(health.currency||'USD')}&intent=capture`;
  script.onload=()=>{state.paypalReady=true; if(state.selected) renderPayPalButtons();};
  script.onerror=()=>toast('Could not load PayPal checkout. Refresh to retry.');
  document.head.appendChild(script);
}
async function refreshOrdersCount(){try{$('#orders-count').textContent=(await api('/api/orders')).length}catch{}}

document.querySelectorAll('.mode').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.mode').forEach(x=>x.classList.remove('active')); b.classList.add('active'); state.mode=b.dataset.mode;
  $('#request').placeholder=state.mode==='individual'?'e.g. A laptop for programming under $900, at least 16 GB RAM and 512 GB storage':'e.g. 100 black cotton T-shirts in sizes S to XL, within a $500 total budget';
}));
document.querySelectorAll('.prompt-chips button').forEach(b=>b.addEventListener('click',()=>{$('#request').value=b.dataset.prompt; if(b.dataset.prompt.includes('100 black')) document.querySelector('[data-mode="business"]').click(); $('#request').focus()}));
$('#find-button').addEventListener('click', async()=>{
  const message=$('#request').value.trim(); if(message.length<3){$('#request').focus();toast('Tell us a little more about what you need.');return}
  const button=$('#find-button'); button.disabled=true;button.innerHTML='Comparing options <span>…</span>';
  try{
    const result=await api('/api/procurement/parse',{method:'POST',body:JSON.stringify({mode:state.mode,message})});
    state.request=message;state.requirements=result.requirements;state.recommendations=result.recommendations;state.aiMode=result.ai_mode;
    renderResults(result); $('#result-section').classList.remove('hidden'); $('#result-section').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){toast(e.message)}finally{button.disabled=false;button.innerHTML='Find options <span>↗</span>'}
});
function renderResults(result){
  const r=result.requirements; $('#result-title').textContent=r.mode==='business'?'Supplier options for your order':'Your best-fit options';
  const specs=Object.entries(r.specifications||{}).map(([k,v])=>`${k.replaceAll('_',' ')}: ${Array.isArray(v)?v.join(', '):v}`);
  $('#brief-card').innerHTML=`<span class="brief-icon">✳</span><div><strong>${esc(r.product_query||r.category)}${r.quantity>1?` · ${r.quantity} units`:''}${r.budget?` · up to ${money(r.budget,r.currency)}`:''}</strong><p>${esc(result.message)}${specs.length?`<br>${esc(specs.join(' · '))}`:''}</p></div><span class="ai-tag">✳ ${esc(result.ai_mode)}</span>`;
  $('#result-count').textContent=`${result.recommendations.length} eligible option${result.recommendations.length===1?'':'s'}`;
  $('#product-grid').innerHTML=result.recommendations.map((p,i)=>productCard(p,i)).join('');
  $('#empty-state').classList.toggle('hidden',result.recommendations.length>0);
  $('#product-grid').classList.toggle('hidden',result.recommendations.length===0);
  document.querySelectorAll('.add-button').forEach(b=>b.addEventListener('click',()=>openCart(result.recommendations[Number(b.dataset.index)])));
}
function productCard(p,index){
  const attr=Object.entries(p.attributes||{}).filter(([,v])=>typeof v!=='object').slice(0,3).map(([k,v])=>`<span class="spec-pill">${esc(k.replaceAll('_',' '))}: ${esc(v)}</span>`).join('');
  const total=p.line_total?money(p.line_total):money(Number(p.unit_price)*(state.requirements?.quantity||1));
  return `<article class="product-card"><div class="product-top"><span class="product-category">${esc(p.category)}</span><span class="product-price">${money(p.unit_price)} <small>/ unit</small></span></div><h3>${esc(p.name)}</h3><div class="product-desc">${esc(p.description)}</div><div class="product-specs">${attr}</div><div class="supplier-row"><span>${esc(p.supplier)}</span><span class="stock-ok">● ${Number(p.stock).toLocaleString()} in demo stock</span></div><div class="supplier-row" style="border-top:0;padding-top:7px"><span>Estimated total</span><strong>${total}</strong></div><button class="add-button" data-index="${index}">Add to ${state.mode==='business'?'purchase draft':'cart'} <span style="float:right">＋</span></button></article>`;
}
function openCart(product){
  state.selected={...product,quantity:Number(state.requirements?.quantity)||1};
  $('#cart-title').textContent=state.mode==='business'?'Purchase-order draft':'Shopping cart';
  $('#cart-currency').textContent=state.requirements?.currency||'USD'; $('#approval').checked=false; $('#paypal-start').disabled=true;
  $('#pay-status').textContent=''; $('#paypal-buttons').innerHTML=''; $('#paypal-start').classList.remove('hidden');
  renderCartLine(); $('#cart-overlay').classList.remove('hidden'); document.body.style.overflow='hidden';
}
function renderCartLine(){
  const p=state.selected;if(!p)return;const total=Number(p.unit_price)*p.quantity;
  $('#cart-lines').innerHTML=`<div class="cart-line"><strong>${esc(p.name)}</strong><span class="line-total">${money(total)}</span><small>${esc(p.supplier)} · ${money(p.unit_price)} each</small><div class="qty-controls"><button id="qty-minus" aria-label="Decrease quantity">−</button><span>${p.quantity} ${p.quantity===1?'item':'items'}</span><button id="qty-plus" aria-label="Increase quantity">＋</button></div></div>`;
  $('#cart-total').textContent=money(total); $('#qty-minus').onclick=()=>changeQty(-1);$('#qty-plus').onclick=()=>changeQty(1);
  $('#paypal-start').disabled=!$('#approval').checked;
  if(state.paypalReady && $('#approval').checked) renderPayPalButtons();
}
function changeQty(delta){const next=state.selected.quantity+delta;if(next<1)return;if(next>state.selected.stock){toast('That quantity exceeds the demo stock.');return}state.selected.quantity=next;renderCartLine()}
$('#approval').addEventListener('change',()=>{ $('#paypal-start').disabled=!$('#approval').checked;if(state.paypalReady&&$('#approval').checked)renderPayPalButtons();else $('#paypal-buttons').innerHTML='';});
function renderPayPalButtons(){
  const box=$('#paypal-buttons');if(!window.paypal||!$('#approval').checked||!state.selected)return;box.innerHTML='';$('#paypal-start').classList.add('hidden');
  window.paypal.Buttons({style:{layout:'vertical',color:'gold',shape:'rect',label:'paypal',height:44},
    createOrder:async()=>{
      const order=await createLocalOrder();state.order=order;localStorage.setItem('procura_pending',JSON.stringify(order));
      const created=await api('/api/payments/create',{method:'POST',body:JSON.stringify({order_id:order.id})});
      localStorage.setItem('procura_paypal',JSON.stringify({order_id:order.id,paypal_order_id:created.paypal_order_id}));return created.paypal_order_id;
    },
    onApprove:async(data)=>{
      $('#pay-status').textContent='Verifying PayPal capture…';
      const pending=JSON.parse(localStorage.getItem('procura_paypal')||'{}');
      try{const result=await api('/api/payments/capture',{method:'POST',body:JSON.stringify({order_id:pending.order_id,paypal_order_id:data.orderID})});$('#pay-status').textContent=result.message;localStorage.removeItem('procura_pending');localStorage.removeItem('procura_paypal');state.order=null;await refreshOrdersCount();setTimeout(()=>{closeCart();switchView('orders');toast('PayPal payment verified. Order is paid.')},1100)}catch(e){$('#pay-status').textContent=e.message}
    },
    onCancel:()=>{$('#pay-status').textContent='Checkout cancelled. Your draft is saved and remains unpaid.'},
    onError:()=>{$('#pay-status').textContent='PayPal checkout had a problem. Your draft is still saved.'}
  }).render(box).catch(()=>{$('#pay-status').textContent='Could not open PayPal checkout.'});
}
async function createLocalOrder(){
  const p=state.selected;
  const order=await api('/api/orders',{method:'POST',body:JSON.stringify({mode:state.mode,items:[{listing_id:p.id,quantity:p.quantity}]})});
  state.order=order;return order;
}
$('#paypal-start').addEventListener('click',async()=>{
  if(!$('#approval').checked||!state.selected)return;
  try{
    if(state.paypalReady){renderPayPalButtons();return}
    const order=await createLocalOrder();await refreshOrdersCount();$('#pay-status').textContent='Draft saved. Add PayPal Sandbox credentials in backend/.env to enable secure checkout.';toast('Purchase draft saved for review.');
  }catch(e){$('#pay-status').textContent=e.message}
});
function closeCart(){$('#cart-overlay').classList.add('hidden');document.body.style.overflow=''}
$('#close-cart').addEventListener('click',closeCart);$('#cart-overlay').addEventListener('click',e=>{if(e.target.id==='cart-overlay')closeCart()});
$('#edit-request').addEventListener('click',()=>{ $('#result-section').classList.add('hidden');$('#request').focus();window.scrollTo({top:0,behavior:'smooth'})});
document.querySelectorAll('.side-item').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));
function switchView(view){
  const orders=view==='orders';$('#procure-view').classList.toggle('hidden',orders);$('#orders-view').classList.toggle('hidden',!orders);$('#crumb').textContent=orders?'Orders':'Procurement';
  document.querySelectorAll('.side-item').forEach(b=>b.classList.toggle('active',b.dataset.view===view));if(orders)loadOrders();
}
async function loadOrders(){
  const list=$('#orders-list');list.innerHTML='<div class="empty-state">Loading orders…</div>';
  try{const orders=await api('/api/orders');if(!orders.length){list.innerHTML='<div class="empty-state"><div>▤</div><strong>No orders yet</strong><p>Your reviewed purchase drafts and PayPal confirmations will appear here.</p></div>';return}
    list.innerHTML=orders.map(o=>`<article class="order-card"><span class="order-icon">${o.mode==='business'?'▦':'◉'}</span><div class="order-main"><strong>${o.mode==='business'?'Business purchase':'Individual purchase'}</strong><small>${o.items.map(x=>`${esc(x.quantity)} × ${esc(x.name)}`).join(' · ')}<br>${new Date(o.created_at).toLocaleString()}</small></div><strong class="order-total">${money(o.total,o.currency)}</strong><span class="status ${esc(o.status)}">${esc(o.status.replaceAll('_',' '))}</span></article>`).join('');
  }catch(e){list.innerHTML=`<div class="empty-state">${esc(e.message)}</div>`}
}
function handlePayPalReturn(){/* PayPal JS SDK returns directly through onApprove; no redirect state to restore. */}
$('#request').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#find-button').click()}});
init();
