const API='';
let state={warehouses:[], rows:[], currentResult:null, currentInvoice:null, currentCaseId:null, lastOpenedAglRef:'', statusRaw:{}, clientLists:{clients:[],brands:[],origins:[],destinations:[],direction_pairs:[]}, dirty:false};
const opFields=[
 ['pallets','Pallets','PLT'],['weight','Gross Weight','KG'],['cbm','CBM','CBM'],['units','Inner Boxes','UNDS'],['master_boxes','Master Boxes','CTNS'],['commercial_value','Commercial Value','USD'],['pedidos_in','Inbound Orders','ORDERS'],['pedidos_out','Outbound Orders','ORDERS'],['storage_days','Storage Days','DAY'],['storage_weeks','Storage Weeks','WEEK'],['storage_months','Storage Months','MONTH']
];
const DEFAULT_BANK_TEXT=`<p>Please pay by Wire Transfer</p><p><b><u>Intermediary Bank:</u></b><br>Standard Chartered Bank, New York<br>1 Madison New York<br>NY 10010-3603, United States<br>Swift: SCBLUS33</p><p><b><u>Beneficiary Bank:</u></b><br>Mercantil Banco, S.A.<br>Calle 50 PH Global Plaza<br>Panamá, Rep. of Panamá<br>Swift: MPANPAPA</p><p><b><u>Beneficiary Account:</u></b><br>Name: America Global Logistics, S.A.<br>Address: Vía España Plaza Liza Piso 3<br>Telephone: +507 366 6900<br>City, Country: Panamá, Rep. of Panamá<br>Beneficiary Account Number: 01202024064</p>`;
const STAFF_NAMES=['VERONICA VILLEGAS','ESTEFANIA GONZALEZ'];
function qs(id){return document.getElementById(id)}
function money(v){const n=Number(String(v??0).replace(/B\/.|B\/|USD|\$|,/g,'').trim());return '$'+(Number.isNaN(n)?0:n).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
function rateFmt(v){
  const n=Number(String(v??0).replace(/B\/.|B\/|USD|\$|,/g,'').trim());
  if(Number.isNaN(n)) return '';
  if(n===0) return '$0.00';

  // Micro tarifas: mantener 4 decimales
  if(Math.abs(n)<0.01) return n.toFixed(4);

  // Tarifas menores a 1: mostrar 2 decimales
  if(Math.abs(n)<1) return n.toFixed(2);

  return '$'+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
function moneySmart(v){
  const n=Number(String(v??0).replace(/B\/.|B\/|USD|\$|,/g,'').trim());
  if(Number.isNaN(n)) return '$0.00';
  if(n!==0 && Math.abs(n)<0.01) return '$'+n.toFixed(4);
  return '$'+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
function smartRound(v){
  const n=Number(String(v??0).replace(/B\/.|B\/|USD|\$|,/g,'').trim());
  if(Number.isNaN(n)) return 0;
  return Number(n.toFixed(n!==0 && Math.abs(n)<0.01 ? 4 : 2));
}
function fmt(v){const n=Number(String(v??0).replace(/B\/.|B\/|USD|\$|,/g,'').trim());return Number.isNaN(n)?(v||''):n.toLocaleString(undefined,{maximumFractionDigits:2})}
function num(v){const n=Number(String(v??'').replace(/B\/.|B\/|USD|\$|,/g,'').trim());return Number.isNaN(n)?0:n}
function normRef(v){return String(v||'').replace(/[^A-Za-z0-9]+/g,'').toUpperCase().trim()}
function shortSavedMessage(payload, created){
  const ref=payload?.agl_ref||payload?.form?.agl_ref||'sin AGL Ref';
  const customer=payload?.customer||payload?.form?.customer||'';
  return (created?'Nuevo expediente creado':'Expediente actualizado')+`: ${ref}`+(customer?` | ${customer}`:'');
}
function markDirty(){state.dirty=true}
function setMsg(t){qs('statusMsg').textContent=t}
let busyCount=0;
function setBusy(on, text='Procesando...'){
  const overlay=qs('busyOverlay');
  const label=qs('busyText');
  if(on){
    busyCount++;
    if(label) label.textContent=text;
    if(overlay){overlay.classList.add('show'); overlay.setAttribute('aria-hidden','false');}
    document.querySelectorAll('button, input, select, textarea').forEach(el=>{
      if(!el.closest('#busyOverlay')) el.disabled=true;
    });
    document.body.classList.add('isBusy');
  }else{
    busyCount=Math.max(0,busyCount-1);
    if(busyCount===0){
      if(overlay){overlay.classList.remove('show'); overlay.setAttribute('aria-hidden','true');}
      document.querySelectorAll('button, input, select, textarea').forEach(el=>el.disabled=false);
      document.body.classList.remove('isBusy');
    }
  }
}
async function withBusy(text, fn){
  if(busyCount>0) return;
  setBusy(true,text);
  try{return await fn();}
  finally{setBusy(false);}
}

function setTab(tab){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));qs(tab).classList.add('active');document.querySelectorAll('.topbar button').forEach(x=>x.classList.remove('active'));let b=qs('tabBtn_'+tab);if(b)b.classList.add('active')}
async function api(path, opts){const r=await fetch(API+path, opts);return await r.json()}
async function loadClientLists(){try{let d=await api('/api/client-lists');state.clientLists=d||{clients:[],brands:[],origins:[],destinations:[],direction_pairs:[]};}catch(e){console.warn(e);state.clientLists={clients:[],brands:[],origins:[],destinations:[],direction_pairs:[]};}}
function optionList(items,value,placeholder='Seleccionar...'){let vals=[...(items||[])].filter(x=>String(x||'').trim());let selected=String(value||'').trim();let has=vals.some(x=>x.toUpperCase()===selected.toUpperCase());let html='';if(!selected){html+=`<option value="" selected disabled>${placeholder}</option>`;}else if(selected&&!has){html+=`<option selected>${esc(selected)}</option>`;}html+=vals.map(v=>`<option ${selected&&v.toUpperCase()===selected.toUpperCase()?'selected':''}>${esc(v)}</option>`).join('');return html;}
async function init(){buildOpRows(); bindDirty(); await loadConfig(); await loadClientLists(); await loadWarehouses(); setTab('formulario');}
function bindDirty(){document.addEventListener('input', e=>{if(e.target.matches('input, select, textarea, [contenteditable=true]')) markDirty()});document.addEventListener('change', e=>{if(e.target.matches('input, select, textarea')) markDirty()})}
function buildOpRows(){qs('opRows').innerHTML=opFields.map(([id,label,unit])=>`<tr><td>${label}</td><td><input id="${id}" value="0" oninput="periods(); renderServicesKeepQty()"></td><td class="unit">${unit}</td></tr>`).join('')}
function clearStatusFields(){state.statusRaw={};['agl_ref'].forEach(id=>{if(qs(id))qs(id).value=''});opFields.forEach(([id])=>{if(qs(id))qs(id).value=''});periods()}
function applyStatusForm(f, ref){clearStatusFields();state.statusRaw=f||{};qs('agl_ref').value=f.agl_ref||ref||'';/* Order to Invoice y Closing No. quedan manuales. */opFields.forEach(([k])=>{if(qs(k))qs(k).value=(f[k]!==undefined&&f[k]!==null)?f[k]:''});periods();renderServices({});}
function periods(){let d=num(qs('storage_days')?.value); if(qs('storage_weeks')) qs('storage_weeks').value=d?fmt(d/7):'0'; if(qs('storage_months')) qs('storage_months').value=d?fmt(d/30):'0'}
async function loadConfig(){let d=await api('/api/config');qs('aglPath').value=d.config.agl_master_path||'';qs('statusPath').value=d.config.status_master_path||'';if(qs('clientPath'))qs('clientPath').value=d.config.client_master_path||'';if(qs('savedDir'))qs('savedDir').value=d.config.saved_dir||'';if(qs('exportsDir'))qs('exportsDir').value=d.config.exports_dir||'';qs('configState').textContent=JSON.stringify(d.state,null,2);setMsg(`Masters cargados | Bodegas: ${d.state.warehouses?.length||0} | Tarifas: ${d.state.rates_count||0}`)}
async function saveConfig(){return withBusy('Guardando rutas y recargando masters...', async()=>{let d=await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agl_master_path:qs('aglPath').value,status_master_path:qs('statusPath').value,client_master_path:qs('clientPath')?.value,saved_dir:qs('savedDir')?.value,exports_dir:qs('exportsDir')?.value})});qs('configState').textContent=JSON.stringify(d,null,2);await loadClientLists();await loadWarehouses();setMsg('Rutas guardadas y masters recargados')})}
async function reloadMasters(){return withBusy('Recargando Masters desde Excel...', async()=>{let d=await api('/api/reload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:true})});await loadConfig();await loadClientLists();await loadWarehouses();setMsg(`Recargado | ${d.rates_count} tarifas | ${d.warehouses.length} bodegas`)})}
async function loadWarehouses(){let d=await api('/api/warehouses');state.warehouses=d.warehouses||[];qs('warehouse').innerHTML=state.warehouses.map(w=>`<option>${w}</option>`).join(''); if(state.warehouses.length){if(!qs('warehouse').value)qs('warehouse').value=state.warehouses[0]; await loadWarehouse();}}
async function loadWarehouse(){let wh=qs('warehouse').value;qs('warehouse_display').value=wh;let d=await api('/api/warehouse/'+encodeURIComponent(wh));state.rows=d.rows||[];renderServicesKeepQty();markDirty()}
function formData(){let f={};['agl_ref','pedido','closing_no'].forEach(id=>{if(qs(id))f[id]=qs(id).value||''});opFields.forEach(([id])=>f[id]=qs(id)?.value||'');Object.assign(f, state.statusRaw||{}); // Status Master gives general fields for closing/invoice.
// Manual values override status values where present.
if(qs('agl_ref')) f.agl_ref=qs('agl_ref').value || f.agl_ref || ''; if(qs('pedido')) { f.pedido=qs('pedido').value || ''; f.invoice_no=f.pedido; } if(qs('closing_no')) f.closing_no=qs('closing_no').value || ''; opFields.forEach(([id])=>f[id]=qs(id)?.value||f[id]||'');return f}
function serviceQtys(){let o={};state.rows.forEach(r=>{let el=qs('qty_'+r.id); if(el) o[String(r.id)]=el.value});return o}
function renderServicesKeepQty(){let old=serviceQtys();renderServices(old)}
function renderServices(old={}){qs('serviceRows').innerHTML=state.rows.map((r,i)=>{let hasSell=(r.sell!==null&&r.sell!==undefined&&String(r.sell).trim()!=='');let hasCost=(r.cost!==null&&r.cost!==undefined&&String(r.cost).trim()!=='');if(!hasSell||!hasCost)return '';/* Autofill desactivado por ahora: las cantidades de servicios se llenan manualmente. */let q=(old[String(r.id)]!==undefined?old[String(r.id)]:'');return `<tr><td class="rownum">${i+1}</td><td>${r.agl_item||r.warehouse_item||''}</td><td><input id="qty_${r.id}" value="${q?fmt(q):''}"></td><td>${r.agl_unit||''}</td><td class="money">${rateFmt(r.sell)}</td><td class="money">${rateFmt(r.cost)}</td><td class="money">${r.minimum_agl?money(r.minimum_agl):''}</td><td class="center"></td></tr>`}).join('')}
function suggestQty(r,f){let unit=(r.agl_unit||'').toUpperCase(), item=(r.agl_item||r.warehouse_item||'').toUpperCase(), period=(r.agl_period||'').toUpperCase();let gv=k=>num(f[k]);if(unit.includes('PALLET')||unit==='PLT')return gv('pallets');if(unit.includes('MASTER BOX')||unit.includes('CTN'))return gv('master_boxes');if(unit.includes('INNER')||unit.includes('SUB BOX')||unit.includes('PAIR')||unit.includes('UNDS'))return gv('units');if(unit.includes('CBM')){let cbm=gv('cbm');if(period.includes('MONTH')||item.includes('MONTH'))return cbm*(gv('storage_months')||1);if(period.includes('WEEK')||item.includes('WEEK'))return cbm*(gv('storage_weeks')||1);if(period.includes('DAY')||item.includes('DAY'))return cbm*(gv('storage_days')||1);return cbm}if(unit.includes('COMMERCIAL VALUE'))return gv('commercial_value');if(unit.includes('DAY'))return gv('storage_days');if(unit.includes('WEEK'))return gv('storage_weeks');if(unit.includes('MONTH'))return gv('storage_months');if(item.includes('WAREHOUSE IN')||item.endsWith(' IN')||item.includes(' IN '))return gv('pedidos_in');if(item.includes('WAREHOUSE OUT')||item.endsWith(' OUT')||item.includes(' OUT '))return gv('pedidos_out');if(item.includes('HANDLING')||item.includes('MANEJO')||unit.includes('SHIPMENT'))return 0;if(item.includes('LABEL')&&(item.includes('MASTER')||item.includes('CARTON')))return gv('master_boxes');if(item.includes('LABEL')&&(item.includes('SUB')||item.includes('INNER')))return gv('units');if(item.includes('LABEL')&&item.includes('PALLET'))return gv('pallets');if(item.includes('SEGREGATION'))return gv('master_boxes');if(item.includes('PICKING'))return gv('units');if(item.includes('PALLET'))return gv('pallets');return 0}
async function searchStatus(){return withBusy('Buscando AGL Ref en Status Master...', async()=>{let ref=qs('searchRef').value.trim()||qs('agl_ref').value.trim();if(!ref){alert('Escribe un AGL Ref');return}setMsg('Buscando en Status Master cargado en memoria...');let d=await api('/api/status/'+encodeURIComponent(ref));if(!d.found){clearStatusFields();qs('searchRef').value=ref;qs('agl_ref').value='';renderServices({});let extra=(d.similar&&d.similar.length)?'\n\nParecidos:\n'+d.similar.join('\n'):'';setMsg(d.message||'No encontrado');alert((d.message||'AGL Ref no encontrada')+extra);markDirty();return}let f=d.form||{};
let newRef=normRef(f.agl_ref||ref);
if(state.currentCaseId && state.lastOpenedAglRef && normRef(state.lastOpenedAglRef)!==newRef){
  state.currentCaseId=null;
}
state.lastOpenedAglRef=newRef;
applyStatusForm(f, ref);setMsg(`Cargado: ${f.agl_ref||ref} | ${f.customer||''} | ${f.brand||''}`);markDirty()})}
async function generateClosing(){return withBusy('Generando cierre...', async()=>{let wh=qs('warehouse').value;let payload={warehouse:wh,form:formData(),service_qtys:serviceQtys()};let result=await api('/api/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.currentResult=result;renderClosing(result);setTab('cierre');markDirty()})}
function esc(v){return String(v??'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]))}
function info(label,value,field=''){return `<div class="infoRow"><b>${label}:</b><span contenteditable="true" ${field?`data-field="${field}" onblur="docFieldBlur(this)"`:''}>${esc(value||'')}</span></div>`}
function staffInfo(label,value,field){let opts=STAFF_NAMES.map(n=>`<option ${String(value||'').trim().toUpperCase()==n.toUpperCase()?'selected':''}>${n}</option>`).join('');return `<div class="infoRow"><b>${label}:</b><select class="docSelect" data-field="${field}" onchange="docSelectChanged(this)">${opts}</select></div>`}
function selectInfo(label,value,field,items,placeholder='Seleccionar...'){return `<div class="infoRow"><b>${label}:</b><select class="docSelect" data-field="${field}" onchange="docSelectChanged(this)">${optionList(items,value,placeholder)}</select></div>`}
function docSelectChanged(el){let f=state.currentResult?.form;if(f){f[el.dataset.field]=el.value;}if(el.dataset.field==='customer'){applyClientLookupFromDoc(el.value)}else if(el.dataset.field==='brand'){applyBrandLookupFromDoc(el.value)}else if(el.dataset.field==='origin'){applyDirectionFromOrigin(el.value)}markDirty()}
function docFieldBlur(el){
  let field=el.dataset.field;
  let val=el.textContent.trim();
  if(state.currentResult?.form){
    state.currentResult.form[field]=val;
    if(field==='commercial_value'){
      const cleanVal=(val||'').replace(/[$,]/g,'').trim();
      state.currentResult.form.commercial_value=cleanVal==='' ? '' : num(cleanVal);
      if(qs('commercial_value')) qs('commercial_value').value=cleanVal==='' ? '' : String(num(cleanVal));
      try{recalcDocTotals()}catch(e){console.warn(e)}
    }
  }
  if(field==='customer'){applyClientLookupFromDoc(val)}
  markDirty()
}
async function applyClientLookupFromDoc(customer){if(!customer)return;try{let brand=state.currentResult?.form?.brand||'';let d=await api('/api/client-lookup?customer='+encodeURIComponent(customer)+'&brand='+encodeURIComponent(brand));if(!d.ok)return;let f=state.currentResult?.form||{};if(d.client_found){f.customer=d.cliente||customer;f.bill_to=d.bill_to||d.cliente||f.bill_to||customer;f.address=d.address||'';f.phone=d.phone||'';f.email=d.email||'';f.payment=d.payment||f.payment||'';f.ruc=d.ruc||'';/* banco por cliente eliminado: usar banco fijo AGL */ f.bank_text='';}if(d.brand_found){f.brand=d.brand||f.brand||'';f.description=d.description||f.description||'';}state.currentResult.form=f;renderClosing(state.currentResult);setMsg('Datos del cliente actualizados desde Client Master');}catch(e){console.warn(e)}}
async function applyBrandLookupFromDoc(brand){if(!brand)return;try{let customer=state.currentResult?.form?.customer||'';let d=await api('/api/client-lookup?customer='+encodeURIComponent(customer)+'&brand='+encodeURIComponent(brand));if(!d.ok)return;let f=state.currentResult?.form||{};if(d.brand_found){f.brand=d.brand||brand;f.description=d.description||'';state.currentResult.form=f;renderClosing(state.currentResult);setMsg('Descripción de marca actualizada desde Client Master');}}catch(e){console.warn(e)}}
function applyDirectionFromOrigin(origin){let f=state.currentResult?.form;if(!f)return;let pairs=state.clientLists?.direction_pairs||[];let found=pairs.find(p=>String(p.origin||'').toUpperCase()===String(origin||'').toUpperCase());if(found){f.destination=found.destination||f.destination||'';renderClosing(state.currentResult);}}
function lineRows(rows,type){return rows.map((r,i)=>`<tr>${type==='cost'?`<td>${r.provider||''}</td>`:''}<td contenteditable="${type==='sale'}">${r.item||''}</td><td contenteditable="${type==='sale'}" onblur="recalcDocTotals()">${fmt(r.qty)}</td><td>${r.unit||''}</td><td contenteditable="${type==='sale'}" onblur="recalcDocTotals()">${rateFmt(r.rate)}</td><td>${r.days||''}</td><td>${moneySmart(r.total)}</td></tr>`).join('')}
function renderClosing(r){let f=r.form||{};let today=new Date().toLocaleDateString('es-PA',{year:'numeric',month:'long',day:'numeric'});let html=`<div class="docHeader closingHeader"><img class="docLogoImg" src="/static/agl_logo.jpg"><div class="company"><b>VÍA ESPAÑA, EDIFICIO PLAZA LIZA, PISO 3, OFICINA #2</b><br>REPÚBLICA DE PANAMÁ<br>TEL.: (507) 366-6900<br>FAX: (507) 264-4680<br>www.americagl.com<br><div class="closingNoBox" contenteditable="true" title="Número de cierre editable">${f.closing_no||''}</div></div></div><div class="bar">CIERRE DE VENTAS</div><div class="info2 closingInfo"><div>${info('Fecha',today,'date')}${info('Para','Contabilidad','to')}${info('Quote No.','','quote_no')}${staffInfo('Vendedor',f.vendor||'','vendor')}${staffInfo('Elaborado por',f.elaborated_by||'','elaborated_by')}${info('Agente',f.agent||'AGL PANAMA','agent')}</div><div>${info('Ref. de Embarque',f.agl_ref,'agl_ref')}${info('Bodega',r.warehouse,'warehouse')}${selectInfo('Cliente',f.customer,'customer',state.clientLists.clients,'Seleccionar cliente')}${info('Facturar a',f.bill_to||f.customer,'bill_to')}${info('Dirección',f.address||'','address')}${info('Teléfono',f.phone||'','phone')}${info('Email',f.email||'','email')}${info('Forma de Pago',f.payment||'CONTADO','payment')}</div></div><div class="bar">DETALLES DEL EMBARQUE</div><div class="info2"><div>${selectInfo('Origen',f.origin,'origin',state.clientLists.origins,'Seleccionar origen')}${selectInfo('Destino',f.destination,'destination',state.clientLists.destinations,'Seleccionar destino')}</div><div>${selectInfo('Marca',f.brand,'brand',state.clientLists.brands,'Seleccionar marca')}${info('Descripción',f.description||'','description')}${info('Pallets',fmt(f.pallets)+' PLT')}${info('Peso Bruto',fmt(f.weight)+' KG')}${info('Cbm',fmt(f.cbm)+' CBM')}${info('Unidades',fmt(f.units)+' UNDS')}${info('Bultos',fmt(f.master_boxes)+' CTNS')}${info('Valor Comercial',money(f.commercial_value||0),'commercial_value')}</div></div><div class="bar">VENTA (FACTURA)</div><table class="docTable" id="salesDoc"><thead><tr><th>ITEM</th><th>CANTIDAD</th><th>UNIDAD DE VENTA</th><th>TARIFA</th><th>DIAS</th><th>TOTAL</th></tr></thead><tbody>${lineRows(r.sales,'sale')}</tbody><tfoot><tr><td colspan="5">TOTAL A FACTURAR</td><td id="saleTotalCell">${moneySmart(r.sale_total)}</td></tr></tfoot></table><div class="bar">COSTO</div><table class="docTable"><thead><tr><th>PROVEEDOR</th><th>ITEM</th><th>CANTIDAD</th><th>UNIDAD</th><th>TARIFA</th><th>DIAS</th><th>TOTAL</th></tr></thead><tbody>${lineRows((r.costs||[]).filter(x=>num(x.rate)!==0),'cost')}</tbody><tfoot><tr><td colspan="6">TOTAL COSTO</td><td>${moneySmart(r.cost_total)}</td></tr></tfoot></table><div class="profit"><b>PROFIT</b><b id="profitCell">${moneySmart(r.profit)}</b></div><table class="metricRows"><tr><td>MARGEN</td><td id="marginCell">${r.margin_pct}%</td></tr><tr><td>FEE LOGÍSTICO</td><td id="feeCell">${r.logistics_fee_pct||0}%</td></tr></table><div class="yellow">Instrucciones Especiales:</div><div class="notes" contenteditable="true">${f.comments||''}</div>`;qs('closingDoc').innerHTML=html}

function syncCommercialValueFromClosing(){
  const el=document.querySelector('#closingDoc [data-field="commercial_value"]');
  if(!state.currentResult) return 0;
  if(el){
    const raw=(el.textContent||'').replace(/[$,]/g,'').trim();
    if(raw===''){
      state.currentResult.form=state.currentResult.form||{};
      state.currentResult.form.commercial_value='';
      if(qs('commercial_value')) qs('commercial_value').value='';
      return 0;
    }
    const cv=num(raw);
    state.currentResult.form=state.currentResult.form||{};
    state.currentResult.form.commercial_value=cv;
    if(qs('commercial_value')) qs('commercial_value').value=String(cv);
    return cv;
  }
  return num(state.currentResult?.form?.commercial_value);
}

function recalcDocTotals(){let total=0;let sales=[];document.querySelectorAll('#salesDoc tbody tr').forEach(tr=>{let tds=tr.querySelectorAll('td');let qty=num(tds[1].textContent);let rate=num(tds[3].textContent);let val=qty*rate;tds[5].textContent=moneySmart(val);total+=val;sales.push({item:tds[0].textContent.trim(),qty,unit:tds[2].textContent.trim(),rate,days:tds[4].textContent.trim(),total:val});});let cost=state.currentResult?.cost_total||0;let profit=total-cost;qs('saleTotalCell').textContent=moneySmart(total);qs('profitCell').textContent=moneySmart(profit);qs('marginCell').textContent=(total?profit/total*100:0).toFixed(2)+'%';let cv=syncCommercialValueFromClosing();
let feePct=Number((cv>0?total/cv*100:0).toFixed(2));
if(qs('feeCell')) qs('feeCell').textContent=feePct.toFixed(2)+'%';
if(state.currentResult){state.currentResult.sales=sales;state.currentResult.sale_total=smartRound(total);state.currentResult.profit=smartRound(profit);state.currentResult.margin_pct=Number((total?profit/total*100:0).toFixed(2));state.currentResult.logistics_fee_pct=feePct;}markDirty()}
function printActive(){setMsg('Abriendo impresión. En el diálogo activa: Más configuración > Gráficos de fondo si tu navegador lo pide.');setTimeout(()=>window.print(),120)}
async function generateInvoice(){return withBusy('Generando factura...', async()=>{if(!state.currentResult){alert('Genera cierre primero');return}recalcDocTotals();let r=state.currentResult,f=r.form||{};let invDate=new Date().toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'2-digit'}).replace(/ /g,'-');let rows=[...document.querySelectorAll('#salesDoc tbody tr')].map(tr=>{let td=tr.querySelectorAll('td');return {item:td[0].textContent,qty:td[1].textContent,rate:td[3].textContent,total:td[5].textContent}});let html=`<div class="invoiceHeader"><div><img class="docLogoImg" src="/static/agl_logo.jpg"><br><b>America Global Logistics S.A.</b><br><small>Tel. 366-69-00 - 366-6949.<br>Fax: 264-2351.<br>Vía España, Plaza Liza, Piso # 3.<br>Panamá, Rep. De Panamá.<br>www.americagl.com</small></div><div class="invoiceNo"><b>Invoice No.</b><br><span contenteditable="true">${f.pedido||''}</span></div></div><div class="invoiceInfo cleanInvoiceInfo invoiceV13"><div class="invCustomer"><b>Customer:</b><div class="customerLines" contenteditable="true">${f.customer||''}<br>${f.address||''}<br>${f.phone||''}<br>${f.email||''}</div></div><div class="invRoute"><div class="invRouteBlock"><b>Origin:</b><div class="invRouteValue" contenteditable="true">${f.origin||''}</div></div><div class="invRouteBlock"><b>Destination:</b><div class="invRouteValue" contenteditable="true">${f.destination||''}</div></div></div><div class="invMeta"><div class="invMetaRow"><b>Date:</b><span contenteditable="true">${invDate}</span></div><div class="invMetaRow"><b>Ref.:</b><span contenteditable="true">${f.agl_ref||''}</span></div><div class="invMetaRow"><b>BRAND:</b><span contenteditable="true">${f.brand||''}</span></div><div class="invShipmentGrid"><span>${fmt(f.pallets)} PLTS</span><span>${fmt(f.weight)} KG</span><span>${fmt(f.cbm)} CBM</span><span>${fmt(f.units)} UNDS</span><span>${fmt(f.master_boxes)} CTNS</span><span></span></div></div></div><table class="invoiceTable" id="invoiceSales"><thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th>Total</th></tr></thead><tbody>${rows.map(x=>`<tr><td contenteditable="true">${x.item}</td><td contenteditable="true" onblur="recalcInvoiceTotals()">${x.qty}</td><td contenteditable="true" onblur="recalcInvoiceTotals()">${x.rate}</td><td>${x.total}</td></tr>`).join('')}</tbody></table><div class="invoiceTotal"><span>USD Amount</span><b id="invoiceTotalCell">${qs('saleTotalCell')?.textContent||moneySmart(r.sale_total)}</b></div><div class="bank">${DEFAULT_BANK_TEXT.replace(/\n/g,'<br>')}</div>`;qs('invoiceDoc').innerHTML=html;state.currentInvoice={html};setTab('factura');markDirty()})}
function recalcInvoiceTotals(){let total=0;document.querySelectorAll('#invoiceSales tbody tr').forEach(tr=>{let tds=tr.querySelectorAll('td');let qty=num(tds[1].textContent);let rate=num(tds[2].textContent);let val=qty*rate;tds[3].textContent=moneySmart(val);total+=val});let cell=qs('invoiceTotalCell');if(cell)cell.textContent=moneySmart(total);markDirty()}

function collectOperationalData(){
  let out={};
  opFields.forEach(([id,label,unit])=>{
    out[id]={label, value:qs(id)?.value||'', unit};
  });
  return out;
}
function collectServicesDetailed(){
  return state.rows.map((r,i)=>{
    let el=qs('qty_'+r.id);
    return {
      id:String(r.id),
      rownum:i+1,
      item:r.agl_item||r.warehouse_item||'',
      warehouse_item:r.warehouse_item||'',
      agl_item:r.agl_item||'',
      qty:el?el.value:'',
      unit:r.agl_unit||'',
      sell:r.sell,
      cost:r.cost,
      minimum_agl:r.minimum_agl,
      raw:r
    };
  });
}
function collectEditedClosingForm(){
  let f={...(state.currentResult?.form||{}), ...formData()};
  document.querySelectorAll('#closingDoc [data-field]').forEach(el=>{
    let key=el.dataset.field;
    if(!key) return;
    if(el.tagName==='SELECT') f[key]=el.value||'';
    else f[key]=(el.textContent||'').trim();
    if(key==='commercial_value'){ const raw=(f[key]||'').replace(/[$,]/g,'').trim(); f[key]=raw==='' ? '' : num(raw); }
  });
  let noBox=document.querySelector('#closingDoc .closingNoBox');
  if(noBox) f.closing_no=(noBox.textContent||'').trim();
  let notes=document.querySelector('#closingDoc .notes');
  if(notes) f.comments=(notes.innerHTML||notes.textContent||'').trim();
  return f;
}
function collectEditedSalesRows(){
  let rows=[];
  document.querySelectorAll('#salesDoc tbody tr').forEach(tr=>{
    let td=tr.querySelectorAll('td');
    if(td.length>=6){
      rows.push({
        item:(td[0].textContent||'').trim(),
        qty:(td[1].textContent||'').trim(),
        unit:(td[2].textContent||'').trim(),
        rate:(td[3].textContent||'').trim(),
        days:(td[4].textContent||'').trim(),
        total:(td[5].textContent||'').trim(),
        qty_num:num(td[1].textContent),
        rate_num:num(td[3].textContent),
        total_num:num(td[5].textContent)
      });
    }
  });
  return rows;
}
function collectEditedCostRows(){
  let rows=[];
  document.querySelectorAll('#closingDoc table.docTable:nth-of-type(2) tbody tr').forEach(tr=>{
    let td=tr.querySelectorAll('td');
    if(td.length>=7){
      rows.push({
        provider:(td[0].textContent||'').trim(),
        item:(td[1].textContent||'').trim(),
        qty:(td[2].textContent||'').trim(),
        unit:(td[3].textContent||'').trim(),
        rate:(td[4].textContent||'').trim(),
        days:(td[5].textContent||'').trim(),
        total:(td[6].textContent||'').trim()
      });
    }
  });
  return rows;
}
function collectEditedInvoiceRows(){
  let rows=[];
  document.querySelectorAll('#invoiceSales tbody tr').forEach(tr=>{
    let td=tr.querySelectorAll('td');
    if(td.length>=4){
      rows.push({
        description:(td[0].textContent||'').trim(),
        qty:(td[1].textContent||'').trim(),
        rate:(td[2].textContent||'').trim(),
        total:(td[3].textContent||'').trim()
      });
    }
  });
  return rows;
}
function collectInvoiceFields(){
  let box={};
  let invNo=document.querySelector('#invoiceDoc .invoiceNo span');
  if(invNo) box.invoice_no=(invNo.textContent||'').trim();
  let total=qs('invoiceTotalCell');
  if(total) box.total=(total.textContent||'').trim();
  let customer=document.querySelector('#invoiceDoc .customerLines');
  if(customer) box.customer_html=customer.innerHTML;
  let routes=[...document.querySelectorAll('#invoiceDoc .invRouteValue')].map(x=>(x.textContent||'').trim());
  if(routes.length){box.origin=routes[0]||''; box.destination=routes[1]||'';}
  let meta=[...document.querySelectorAll('#invoiceDoc .invMetaRow span')].map(x=>(x.textContent||'').trim());
  if(meta.length){box.date=meta[0]||''; box.ref=meta[1]||''; box.brand=meta[2]||'';}
  return box;
}
function restoreOperationalData(operational){
  if(!operational) return;
  opFields.forEach(([id])=>{
    let v=operational[id];
    if(qs(id)){
      if(v && typeof v==='object') qs(id).value=v.value??'';
      else if(v!==undefined) qs(id).value=v;
    }
  });
  periods();
}
function restoreServiceQtys(savedQtys){
  savedQtys=savedQtys||{};
  Object.keys(savedQtys).forEach(k=>{
    let el=qs('qty_'+k);
    if(el) el.value=savedQtys[k]??'';
  });
}

function collectCase(){
  if(qs('salesDoc')){try{recalcDocTotals()}catch(e){console.warn(e)}}
  if(qs('invoiceSales')){try{recalcInvoiceTotals()}catch(e){console.warn(e)}}
  let f=collectEditedClosingForm();
  let currentRefNorm=normRef(f.agl_ref||'');
  let openedRefNorm=normRef(state.lastOpenedAglRef||'');
  let shouldCreateNew=!!(state.currentCaseId && openedRefNorm && currentRefNorm && openedRefNorm!==currentRefNorm);
  let closingHtml=qs('closingDoc')?.innerHTML||'';
  let invoiceHtml=qs('invoiceDoc')?.innerHTML||'';
  let payload={
    case_id:shouldCreateNew?null:state.currentCaseId,
    agl_ref:f.agl_ref||'',
    customer:f.customer||f.bill_to||'',
    warehouse:qs('warehouse')?.value||f.warehouse||'',
    date:new Date().toISOString().slice(0,10),
    form:f,
    status_raw:state.statusRaw||{},
    operational_data:collectOperationalData(),
    service_qtys:serviceQtys(),
    services_detailed:collectServicesDetailed(),
    result:state.currentResult,
    edited_sales:collectEditedSalesRows(),
    edited_costs:collectEditedCostRows(),
    invoice_rows:collectEditedInvoiceRows(),
    invoice_fields:collectInvoiceFields(),
    closing_html:closingHtml,
    invoice_html:invoiceHtml,
    has_closing:!!closingHtml,
    has_invoice:!!invoiceHtml,
    selected_warehouse:qs('warehouse')?.value||'',
    metadata:{
      saved_at:new Date().toISOString(),
      app:'AGL Closing System',
      save_mode:'full_snapshot_supabase',
      note:'Guarda formulario, operational data, services, cierre editado, factura editada y HTML final.'
    }
  };
  return payload;
}
async function saveCaseFile(){return withBusy('Guardando expediente...', async()=>{
  let payload=collectCase();
  if(!payload.agl_ref && !confirm('No hay AGL Ref. ¿Guardar como borrador?'))return;
  let wasNew=!payload.case_id;
  let d=await api('/api/save-case',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  state.currentCaseId=d.id||d.case_id||state.currentCaseId;
  state.lastOpenedAglRef=payload.agl_ref||state.lastOpenedAglRef||'';
  state.dirty=false;
  let msg=shortSavedMessage(payload, wasNew || d.created===true);
  setMsg('✅ '+msg);
  alert('✅ '+msg);
})}
async function loadCases(){return withBusy('Buscando expedientes guardados...', async()=>{
  let q=qs('docSearch').value;
  let d=await api('/api/cases?q='+encodeURIComponent(q));
  qs('documentsList').innerHTML=(d.cases||[]).map(x=>{
    let fname=x.filename||`case_${x.id}.json`;
    return `<div class="docCard"><div><b>${x.title||''}</b><br>${x.agl_ref||''} | ${x.customer||''} | ${x.warehouse||''} | ${x.updated_at||''}</div><button class="actionBtn" onclick="openCase(${x.id})">Abrir</button></div>`;
  }).join('')
})}
async function openCase(id){return withBusy('Abriendo expediente...', async()=>{
  let d=await api('/api/cases/'+id);
  if(!d.found){alert('No encontrado');return}

  // Soporta respuestas antiguas y nuevas:
  // {case:{payload:{...}}}, {case:{...payload directo...}} o {payload:{...}}
  let p=(d.case&&d.case.payload)?d.case.payload:(d.payload?d.payload:(d.case||{}));
  if(!p || typeof p!=='object') p={};

  state.currentCaseId=id;
  state.lastOpenedAglRef=p.form?.agl_ref||p.agl_ref||'';
  state.statusRaw=p.status_raw||p.form||{};
  state.currentResult=p.result||null;
  state.currentInvoice=p.invoice_fields?{fields:p.invoice_fields, rows:p.invoice_rows||[]}:null;

  // Restaurar bodega primero para cargar las tarifas correctas.
  let wh=p.selected_warehouse||p.warehouse||p.form?.warehouse||'';
  if(wh&&qs('warehouse')){
    qs('warehouse').value=wh;
    qs('warehouse_display').value=wh;
    await loadWarehouse();
  }

  // Restaurar formulario completo después de cargar bodega, para que nada lo pise.
  if(p.form){
    Object.keys(p.form).forEach(k=>{if(qs(k))qs(k).value=p.form[k]??''});
  }
  restoreOperationalData(p.operational_data);
  restoreServiceQtys(p.service_qtys);

  // Reforzar campos principales.
  if(qs('agl_ref')) qs('agl_ref').value=p.form?.agl_ref||p.agl_ref||qs('agl_ref').value||'';
  if(qs('pedido')) qs('pedido').value=p.form?.pedido||p.form?.invoice_no||qs('pedido').value||'';
  if(qs('closing_no')) qs('closing_no').value=p.form?.closing_no||qs('closing_no').value||'';
  if(qs('warehouse_display')) qs('warehouse_display').value=wh||qs('warehouse')?.value||'';

  qs('closingDoc').innerHTML=p.closing_html||'';
  qs('invoiceDoc').innerHTML=p.invoice_html||'';

  // Abrir siempre en Formulario para que sea cómodo revisar o continuar.
  setTab('formulario');
  state.dirty=false;
  let fname=d.case?.filename||p.filename||`case_${id}.json`;
  setMsg('Expediente abierto completo: '+fname);
})}
async function newClosing(){if(busyCount>0)return;if(state.dirty){let yn=confirm('¿Deseas guardar el expediente actual antes de crear uno nuevo?');if(yn) await saveCaseFile()}return withBusy('Preparando nuevo cierre...', async()=>{state={warehouses:state.warehouses,rows:state.rows,clientLists:state.clientLists,currentResult:null,currentInvoice:null,currentCaseId:null,lastOpenedAglRef:'',statusRaw:{},dirty:false};['searchRef','agl_ref','pedido','closing_no'].forEach(id=>{if(qs(id))qs(id).value=''});opFields.forEach(([id])=>{if(qs(id))qs(id).value='0'});qs('closingDoc').innerHTML='';qs('invoiceDoc').innerHTML='';periods();renderServices({});setTab('formulario');setMsg('Nuevo cierre listo')})}
window.addEventListener('load',init);
