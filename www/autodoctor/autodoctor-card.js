/******************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
/* global Reflect, Promise, SuppressedError, Symbol, Iterator */


function __decorate(decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
}

typeof SuppressedError === "function" ? SuppressedError : function (error, suppressed, message) {
    var e = new Error(message);
    return e.name = "SuppressedError", e.error = error, e.suppressed = suppressed, e;
};

/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const t$2=globalThis,e$2=t$2.ShadowRoot&&(void 0===t$2.ShadyCSS||t$2.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s$2=Symbol(),o$4=new WeakMap;let n$3 = class n{constructor(t,e,o){if(this._$cssResult$=true,o!==s$2)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e;}get styleSheet(){let t=this.o;const s=this.t;if(e$2&&void 0===t){const e=void 0!==s&&1===s.length;e&&(t=o$4.get(s)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),e&&o$4.set(s,t));}return t}toString(){return this.cssText}};const r$4=t=>new n$3("string"==typeof t?t:t+"",void 0,s$2),i$3=(t,...e)=>{const o=1===t.length?t[0]:e.reduce((e,s,o)=>e+(t=>{if(true===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[o+1],t[0]);return new n$3(o,t,s$2)},S$1=(s,o)=>{if(e$2)s.adoptedStyleSheets=o.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const e of o){const o=document.createElement("style"),n=t$2.litNonce;void 0!==n&&o.setAttribute("nonce",n),o.textContent=e.cssText,s.appendChild(o);}},c$2=e$2?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const s of t.cssRules)e+=s.cssText;return r$4(e)})(t):t;

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const{is:i$2,defineProperty:e$1,getOwnPropertyDescriptor:h$1,getOwnPropertyNames:r$3,getOwnPropertySymbols:o$3,getPrototypeOf:n$2}=Object,a$1=globalThis,c$1=a$1.trustedTypes,l$1=c$1?c$1.emptyScript:"",p$1=a$1.reactiveElementPolyfillSupport,d$1=(t,s)=>t,u$1={toAttribute(t,s){switch(s){case Boolean:t=t?l$1:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t);}return t},fromAttribute(t,s){let i=t;switch(s){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t);}catch(t){i=null;}}return i}},f$1=(t,s)=>!i$2(t,s),b$1={attribute:true,type:String,converter:u$1,reflect:false,useDefault:false,hasChanged:f$1};Symbol.metadata??=Symbol("metadata"),a$1.litPropertyMetadata??=new WeakMap;let y$1 = class y extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t);}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,s=b$1){if(s.state&&(s.attribute=false),this._$Ei(),this.prototype.hasOwnProperty(t)&&((s=Object.create(s)).wrapped=true),this.elementProperties.set(t,s),!s.noAccessor){const i=Symbol(),h=this.getPropertyDescriptor(t,i,s);void 0!==h&&e$1(this.prototype,t,h);}}static getPropertyDescriptor(t,s,i){const{get:e,set:r}=h$1(this.prototype,t)??{get(){return this[s]},set(t){this[s]=t;}};return {get:e,set(s){const h=e?.call(this);r?.call(this,s),this.requestUpdate(t,h,i);},configurable:true,enumerable:true}}static getPropertyOptions(t){return this.elementProperties.get(t)??b$1}static _$Ei(){if(this.hasOwnProperty(d$1("elementProperties")))return;const t=n$2(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties);}static finalize(){if(this.hasOwnProperty(d$1("finalized")))return;if(this.finalized=true,this._$Ei(),this.hasOwnProperty(d$1("properties"))){const t=this.properties,s=[...r$3(t),...o$3(t)];for(const i of s)this.createProperty(i,t[i]);}const t=this[Symbol.metadata];if(null!==t){const s=litPropertyMetadata.get(t);if(void 0!==s)for(const[t,i]of s)this.elementProperties.set(t,i);}this._$Eh=new Map;for(const[t,s]of this.elementProperties){const i=this._$Eu(t,s);void 0!==i&&this._$Eh.set(i,t);}this.elementStyles=this.finalizeStyles(this.styles);}static finalizeStyles(s){const i=[];if(Array.isArray(s)){const e=new Set(s.flat(1/0).reverse());for(const s of e)i.unshift(c$2(s));}else void 0!==s&&i.push(c$2(s));return i}static _$Eu(t,s){const i=s.attribute;return  false===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=false,this.hasUpdated=false,this._$Em=null,this._$Ev();}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this));}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.();}removeController(t){this._$EO?.delete(t);}_$E_(){const t=new Map,s=this.constructor.elementProperties;for(const i of s.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t);}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return S$1(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(true),this._$EO?.forEach(t=>t.hostConnected?.());}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.());}attributeChangedCallback(t,s,i){this._$AK(t,i);}_$ET(t,s){const i=this.constructor.elementProperties.get(t),e=this.constructor._$Eu(t,i);if(void 0!==e&&true===i.reflect){const h=(void 0!==i.converter?.toAttribute?i.converter:u$1).toAttribute(s,i.type);this._$Em=t,null==h?this.removeAttribute(e):this.setAttribute(e,h),this._$Em=null;}}_$AK(t,s){const i=this.constructor,e=i._$Eh.get(t);if(void 0!==e&&this._$Em!==e){const t=i.getPropertyOptions(e),h="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:u$1;this._$Em=e;const r=h.fromAttribute(s,t.type);this[e]=r??this._$Ej?.get(e)??r,this._$Em=null;}}requestUpdate(t,s,i,e=false,h){if(void 0!==t){const r=this.constructor;if(false===e&&(h=this[t]),i??=r.getPropertyOptions(t),!((i.hasChanged??f$1)(h,s)||i.useDefault&&i.reflect&&h===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,i))))return;this.C(t,s,i);} false===this.isUpdatePending&&(this._$ES=this._$EP());}C(t,s,{useDefault:i,reflect:e,wrapped:h},r){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??s??this[t]),true!==h||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||i||(s=void 0),this._$AL.set(t,s)),true===e&&this._$Em!==t&&(this._$Eq??=new Set).add(t));}async _$EP(){this.isUpdatePending=true;try{await this._$ES;}catch(t){Promise.reject(t);}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,s]of this._$Ep)this[t]=s;this._$Ep=void 0;}const t=this.constructor.elementProperties;if(t.size>0)for(const[s,i]of t){const{wrapped:t}=i,e=this[s];true!==t||this._$AL.has(s)||void 0===e||this.C(s,void 0,i,e);}}let t=false;const s=this._$AL;try{t=this.shouldUpdate(s),t?(this.willUpdate(s),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(s)):this._$EM();}catch(s){throw t=false,this._$EM(),s}t&&this._$AE(s);}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=true,this.firstUpdated(t)),this.updated(t);}_$EM(){this._$AL=new Map,this.isUpdatePending=false;}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return  true}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM();}updated(t){}firstUpdated(t){}};y$1.elementStyles=[],y$1.shadowRootOptions={mode:"open"},y$1[d$1("elementProperties")]=new Map,y$1[d$1("finalized")]=new Map,p$1?.({ReactiveElement:y$1}),(a$1.reactiveElementVersions??=[]).push("2.1.2");

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const t$1=globalThis,i$1=t=>t,s$1=t$1.trustedTypes,e=s$1?s$1.createPolicy("lit-html",{createHTML:t=>t}):void 0,h="$lit$",o$2=`lit$${Math.random().toFixed(9).slice(2)}$`,n$1="?"+o$2,r$2=`<${n$1}>`,l=document,c=()=>l.createComment(""),a=t=>null===t||"object"!=typeof t&&"function"!=typeof t,u=Array.isArray,d=t=>u(t)||"function"==typeof t?.[Symbol.iterator],f="[ \t\n\f\r]",v=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,_=/-->/g,m=/>/g,p=RegExp(`>|${f}(?:([^\\s"'>=/]+)(${f}*=${f}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),g=/'/g,$=/"/g,y=/^(?:script|style|textarea|title)$/i,x=t=>(i,...s)=>({_$litType$:t,strings:i,values:s}),b=x(1),E=Symbol.for("lit-noChange"),A=Symbol.for("lit-nothing"),C=new WeakMap,P=l.createTreeWalker(l,129);function V(t,i){if(!u(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==e?e.createHTML(i):i}const N=(t,i)=>{const s=t.length-1,e=[];let n,l=2===i?"<svg>":3===i?"<math>":"",c=v;for(let i=0;i<s;i++){const s=t[i];let a,u,d=-1,f=0;for(;f<s.length&&(c.lastIndex=f,u=c.exec(s),null!==u);)f=c.lastIndex,c===v?"!--"===u[1]?c=_:void 0!==u[1]?c=m:void 0!==u[2]?(y.test(u[2])&&(n=RegExp("</"+u[2],"g")),c=p):void 0!==u[3]&&(c=p):c===p?">"===u[0]?(c=n??v,d=-1):void 0===u[1]?d=-2:(d=c.lastIndex-u[2].length,a=u[1],c=void 0===u[3]?p:'"'===u[3]?$:g):c===$||c===g?c=p:c===_||c===m?c=v:(c=p,n=void 0);const x=c===p&&t[i+1].startsWith("/>")?" ":"";l+=c===v?s+r$2:d>=0?(e.push(a),s.slice(0,d)+h+s.slice(d)+o$2+x):s+o$2+(-2===d?i:x);}return [V(t,l+(t[s]||"<?>")+(2===i?"</svg>":3===i?"</math>":"")),e]};class S{constructor({strings:t,_$litType$:i},e){let r;this.parts=[];let l=0,a=0;const u=t.length-1,d=this.parts,[f,v]=N(t,i);if(this.el=S.createElement(f,e),P.currentNode=this.el.content,2===i||3===i){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes);}for(;null!==(r=P.nextNode())&&d.length<u;){if(1===r.nodeType){if(r.hasAttributes())for(const t of r.getAttributeNames())if(t.endsWith(h)){const i=v[a++],s=r.getAttribute(t).split(o$2),e=/([.?@])?(.*)/.exec(i);d.push({type:1,index:l,name:e[2],strings:s,ctor:"."===e[1]?I:"?"===e[1]?L:"@"===e[1]?z:H}),r.removeAttribute(t);}else t.startsWith(o$2)&&(d.push({type:6,index:l}),r.removeAttribute(t));if(y.test(r.tagName)){const t=r.textContent.split(o$2),i=t.length-1;if(i>0){r.textContent=s$1?s$1.emptyScript:"";for(let s=0;s<i;s++)r.append(t[s],c()),P.nextNode(),d.push({type:2,index:++l});r.append(t[i],c());}}}else if(8===r.nodeType)if(r.data===n$1)d.push({type:2,index:l});else {let t=-1;for(;-1!==(t=r.data.indexOf(o$2,t+1));)d.push({type:7,index:l}),t+=o$2.length-1;}l++;}}static createElement(t,i){const s=l.createElement("template");return s.innerHTML=t,s}}function M(t,i,s=t,e){if(i===E)return i;let h=void 0!==e?s._$Co?.[e]:s._$Cl;const o=a(i)?void 0:i._$litDirective$;return h?.constructor!==o&&(h?._$AO?.(false),void 0===o?h=void 0:(h=new o(t),h._$AT(t,s,e)),void 0!==e?(s._$Co??=[])[e]=h:s._$Cl=h),void 0!==h&&(i=M(t,h._$AS(t,i.values),h,e)),i}class R{constructor(t,i){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=i;}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:i},parts:s}=this._$AD,e=(t?.creationScope??l).importNode(i,true);P.currentNode=e;let h=P.nextNode(),o=0,n=0,r=s[0];for(;void 0!==r;){if(o===r.index){let i;2===r.type?i=new k(h,h.nextSibling,this,t):1===r.type?i=new r.ctor(h,r.name,r.strings,this,t):6===r.type&&(i=new Z(h,this,t)),this._$AV.push(i),r=s[++n];}o!==r?.index&&(h=P.nextNode(),o++);}return P.currentNode=l,e}p(t){let i=0;for(const s of this._$AV) void 0!==s&&(void 0!==s.strings?(s._$AI(t,s,i),i+=s.strings.length-2):s._$AI(t[i])),i++;}}class k{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,i,s,e){this.type=2,this._$AH=A,this._$AN=void 0,this._$AA=t,this._$AB=i,this._$AM=s,this.options=e,this._$Cv=e?.isConnected??true;}get parentNode(){let t=this._$AA.parentNode;const i=this._$AM;return void 0!==i&&11===t?.nodeType&&(t=i.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,i=this){t=M(this,t,i),a(t)?t===A||null==t||""===t?(this._$AH!==A&&this._$AR(),this._$AH=A):t!==this._$AH&&t!==E&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):d(t)?this.k(t):this._(t);}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t));}_(t){this._$AH!==A&&a(this._$AH)?this._$AA.nextSibling.data=t:this.T(l.createTextNode(t)),this._$AH=t;}$(t){const{values:i,_$litType$:s}=t,e="number"==typeof s?this._$AC(t):(void 0===s.el&&(s.el=S.createElement(V(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===e)this._$AH.p(i);else {const t=new R(e,this),s=t.u(this.options);t.p(i),this.T(s),this._$AH=t;}}_$AC(t){let i=C.get(t.strings);return void 0===i&&C.set(t.strings,i=new S(t)),i}k(t){u(this._$AH)||(this._$AH=[],this._$AR());const i=this._$AH;let s,e=0;for(const h of t)e===i.length?i.push(s=new k(this.O(c()),this.O(c()),this,this.options)):s=i[e],s._$AI(h),e++;e<i.length&&(this._$AR(s&&s._$AB.nextSibling,e),i.length=e);}_$AR(t=this._$AA.nextSibling,s){for(this._$AP?.(false,true,s);t!==this._$AB;){const s=i$1(t).nextSibling;i$1(t).remove(),t=s;}}setConnected(t){ void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t));}}class H{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,i,s,e,h){this.type=1,this._$AH=A,this._$AN=void 0,this.element=t,this.name=i,this._$AM=e,this.options=h,s.length>2||""!==s[0]||""!==s[1]?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=A;}_$AI(t,i=this,s,e){const h=this.strings;let o=false;if(void 0===h)t=M(this,t,i,0),o=!a(t)||t!==this._$AH&&t!==E,o&&(this._$AH=t);else {const e=t;let n,r;for(t=h[0],n=0;n<h.length-1;n++)r=M(this,e[s+n],i,n),r===E&&(r=this._$AH[n]),o||=!a(r)||r!==this._$AH[n],r===A?t=A:t!==A&&(t+=(r??"")+h[n+1]),this._$AH[n]=r;}o&&!e&&this.j(t);}j(t){t===A?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"");}}class I extends H{constructor(){super(...arguments),this.type=3;}j(t){this.element[this.name]=t===A?void 0:t;}}class L extends H{constructor(){super(...arguments),this.type=4;}j(t){this.element.toggleAttribute(this.name,!!t&&t!==A);}}class z extends H{constructor(t,i,s,e,h){super(t,i,s,e,h),this.type=5;}_$AI(t,i=this){if((t=M(this,t,i,0)??A)===E)return;const s=this._$AH,e=t===A&&s!==A||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,h=t!==A&&(s===A||e);e&&this.element.removeEventListener(this.name,this,s),h&&this.element.addEventListener(this.name,this,t),this._$AH=t;}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t);}}class Z{constructor(t,i,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=i,this.options=s;}get _$AU(){return this._$AM._$AU}_$AI(t){M(this,t);}}const B=t$1.litHtmlPolyfillSupport;B?.(S,k),(t$1.litHtmlVersions??=[]).push("3.3.2");const D=(t,i,s)=>{const e=s?.renderBefore??i;let h=e._$litPart$;if(void 0===h){const t=s?.renderBefore??null;e._$litPart$=h=new k(i.insertBefore(c(),t),t,void 0,s??{});}return h._$AI(t),h};

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const s=globalThis;class i extends y$1{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0;}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const r=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=D(r,this.renderRoot,this.renderOptions);}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(true);}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(false);}render(){return E}}i._$litElement$=true,i["finalized"]=true,s.litElementHydrateSupport?.({LitElement:i});const o$1=s.litElementPolyfillSupport;o$1?.({LitElement:i});(s.litElementVersions??=[]).push("4.2.2");

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const t=t=>(e,o)=>{ void 0!==o?o.addInitializer(()=>{customElements.define(t,e);}):customElements.define(t,e);};

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const o={attribute:true,type:String,converter:u$1,reflect:false,hasChanged:f$1},r$1=(t=o,e,r)=>{const{kind:n,metadata:i}=r;let s=globalThis.litPropertyMetadata.get(i);if(void 0===s&&globalThis.litPropertyMetadata.set(i,s=new Map),"setter"===n&&((t=Object.create(t)).wrapped=true),s.set(r.name,t),"accessor"===n){const{name:o}=r;return {set(r){const n=e.get.call(this);e.set.call(this,r),this.requestUpdate(o,n,t,true,r);},init(e){return void 0!==e&&this.C(o,void 0,t,e),e}}}if("setter"===n){const{name:o}=r;return function(r){const n=this[o];e.call(this,r),this.requestUpdate(o,n,t,true,r);}}throw Error("Unsupported decorator location: "+n)};function n(t){return (e,o)=>"object"==typeof o?r$1(t,e,o):((t,e,o)=>{const r=e.hasOwnProperty(o);return e.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(e,o):void 0})(t,e,o)}

/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function r(r){return n({...r,state:true,attribute:false})}

function getSuggestionKey(issue) {
    return `${issue.automation_id}:${issue.entity_id}:${issue.message}`;
}

/**
 * Design tokens and host styles shared by all autodoctor components.
 * Every component should include this in its styles array.
 */
const autodocTokens = i$3 `
  :host {
    /* Typography */
    --autodoc-title-size: 1.1rem;
    --autodoc-name-size: 0.95rem;
    --autodoc-issue-size: 0.875rem;
    --autodoc-meta-size: 0.8rem;

    /* Colors */
    --autodoc-error: #d94848;
    --autodoc-warning: #c49008;
    --autodoc-success: #2e8b57;

    /* Spacing */
    --autodoc-spacing-xs: 4px;
    --autodoc-spacing-sm: 8px;
    --autodoc-spacing-md: 12px;
    --autodoc-spacing-lg: 16px;
    --autodoc-spacing-xl: 24px;

    /* Transitions */
    --autodoc-transition-fast: 150ms ease;
    --autodoc-transition-normal: 200ms ease;
  }

  @media (prefers-reduced-motion: reduce) {
    :host {
      --autodoc-transition-fast: 0ms;
      --autodoc-transition-normal: 0ms;
    }
  }

  :host {
    display: block;
    width: 100%;
    box-sizing: border-box;
  }

  /* Mobile: larger text for readability */
  @media (max-width: 600px) {
    :host {
      --autodoc-title-size: 1.25rem;
      --autodoc-name-size: 1.05rem;
      --autodoc-issue-size: 1rem;
      --autodoc-meta-size: 0.9rem;
    }
  }
`;
/**
 * Badge row styles: error/warning/healthy/suppressed pills with counts.
 */
const badgeStyles = i$3 `
  /* Badges row (in content area) */
  .badges-row {
    display: flex;
    gap: var(--autodoc-spacing-sm);
    margin-bottom: var(--autodoc-spacing-md);
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: var(--autodoc-meta-size);
    font-weight: 600;
    transition: transform var(--autodoc-transition-fast);
    cursor: default;
  }

  .badge:hover {
    transform: scale(1.05);
  }

  .badge-icon {
    font-size: 0.7em;
  }

  .badge-error {
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
  }

  .badge-warning {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .badge-healthy {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }

  .badge-suppressed {
    background: rgba(127, 127, 127, 0.15);
    color: var(--secondary-text-color);
    margin-left: auto;
  }

  .badge-active {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
  }

  /* Mobile: larger tap targets for badges */
  @media (max-width: 600px) {
    .badge {
      padding: 6px 12px;
      font-size: var(--autodoc-issue-size);
      min-height: 36px;
    }

    .badge-icon {
      font-size: 1em;
    }

    .badges-row {
      flex-wrap: wrap;
    }
  }

`;
/**
 * Issue group styles: automation group container, issues, fix suggestions,
 * confidence pills, suppress/dismiss buttons, edit links.
 */
const issueGroupStyles = i$3 `
  /* Automation groups */
  .automation-group {
    background: rgba(127, 127, 127, 0.06);
    border-left: 3px solid var(--autodoc-error);
    border-radius: 0 8px 8px 0;
    padding: var(--autodoc-spacing-md);
    margin-bottom: var(--autodoc-spacing-md);
  }

  .automation-group:last-child {
    margin-bottom: 0;
  }

  .automation-group.has-warning {
    border-left-color: var(--autodoc-warning);
  }

  .automation-header {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
  }

  .automation-severity-icon {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
    border-radius: 50%;
    font-size: 0.7rem;
    font-weight: bold;
  }

  .automation-group.has-warning .automation-severity-icon {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .automation-name {
    flex: 1;
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--primary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .automation-badge {
    background: var(--autodoc-error);
    color: #fff;
    font-size: var(--autodoc-meta-size);
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    min-width: 18px;
    text-align: center;
  }

  .automation-group.has-warning .automation-badge {
    background: var(--autodoc-warning);
  }

  /* Issues */
  .automation-issues {
    margin-top: var(--autodoc-spacing-md);
    padding-left: 28px;
  }

  .issue {
    padding: var(--autodoc-spacing-sm) 0;
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.15));
  }

  .issue:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .issue-header {
    display: flex;
    align-items: flex-start;
    gap: var(--autodoc-spacing-sm);
  }

  .issue-icon {
    flex-shrink: 0;
    font-size: 0.65rem;
    font-weight: bold;
    margin-top: 3px;
  }

  .issue.error .issue-icon {
    color: var(--autodoc-error);
  }

  .issue.warning .issue-icon {
    color: var(--autodoc-warning);
  }

  .issue-message {
    flex: 1;
    font-size: var(--autodoc-issue-size);
    color: var(--secondary-text-color);
    line-height: 1.4;
    word-break: break-word;
  }

  .suppress-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: var(--secondary-text-color);
    font-size: 0.75rem;
    cursor: pointer;
    opacity: 0.6;
    transition:
      opacity var(--autodoc-transition-fast),
      background var(--autodoc-transition-fast);
  }

  .suppress-btn:hover {
    opacity: 1;
    background: var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .suppress-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
    opacity: 1;
  }

  /* Fix suggestions */
  .fix-suggestion {
    display: flex;
    align-items: flex-start;
    gap: var(--autodoc-spacing-sm);
    margin-top: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    background: var(--primary-background-color, rgba(255, 255, 255, 0.5));
    border-radius: 6px;
  }

  .fix-icon {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
  }

  .fix-content {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
  }

  .fix-description {
    font-size: var(--autodoc-issue-size);
    color: var(--primary-text-color);
    line-height: 1.4;
  }

  .fix-replacement {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--autodoc-meta-size);
  }

  .fix-before,
  .fix-after {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: rgba(127, 127, 127, 0.12);
    border-radius: 4px;
    padding: 1px 5px;
  }

  .fix-after {
    background: rgba(46, 139, 87, 0.12);
    color: var(--autodoc-success);
  }

  .fix-arrow {
    color: var(--secondary-text-color);
  }

  .fix-reason {
    display: block;
    width: 100%;
    font-size: var(--autodoc-meta-size);
    color: var(--secondary-text-color);
  }

  .fix-actions {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .copy-fix-btn,
  .apply-fix-btn {
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
    border-radius: 5px;
    background: transparent;
    padding: 2px 8px;
    font-size: var(--autodoc-meta-size);
    cursor: pointer;
    color: var(--secondary-text-color);
    transition: background var(--autodoc-transition-fast);
  }

  .copy-fix-btn:hover,
  .apply-fix-btn:hover {
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
  }

  .apply-fix-btn {
    color: var(--primary-color);
    border-color: rgba(var(--rgb-primary-color, 66, 133, 244), 0.4);
  }

  .confidence-pill {
    display: inline-block;
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 10px;
  }

  .confidence-pill.high {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }

  .confidence-pill.medium {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }

  .dismiss-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: var(--secondary-text-color);
    font-size: 0.7rem;
    cursor: pointer;
    opacity: 0.6;
    transition:
      opacity var(--autodoc-transition-fast),
      background var(--autodoc-transition-fast);
  }

  .dismiss-btn:hover {
    opacity: 1;
    background: var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .dismiss-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 1px;
    opacity: 1;
  }

  /* Edit link */
  .edit-link {
    display: inline-flex;
    align-items: center;
    gap: var(--autodoc-spacing-xs);
    margin-top: var(--autodoc-spacing-md);
    margin-left: 28px;
    color: var(--primary-color);
    text-decoration: none;
    font-size: var(--autodoc-issue-size);
    transition: gap var(--autodoc-transition-fast);
  }

  .edit-link:hover {
    text-decoration: underline;
    gap: var(--autodoc-spacing-sm);
  }

  .edit-link:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
    border-radius: 2px;
  }

  .edit-arrow {
    transition: transform var(--autodoc-transition-fast);
  }

  .edit-link:hover .edit-arrow {
    transform: translateX(2px);
  }

  /* Mobile: suppress/dismiss label visibility */
  .suppress-label,
  .dismiss-label {
    display: none;
  }

  /* Mobile: touch-friendly issue groups */
  @media (max-width: 600px) {
    .automation-issues {
      padding-left: 16px;
    }

    .automation-severity-icon {
      width: 24px;
      height: 24px;
      font-size: 0.8rem;
    }

    /* Suppress button: show label, 44px touch target */
    .suppress-btn {
      width: auto;
      min-width: 44px;
      min-height: 44px;
      padding: 8px 10px;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 6px;
      opacity: 0.7;
    }

    .suppress-label {
      display: inline;
      font-size: var(--autodoc-meta-size);
    }

    /* Dismiss button: 44px touch target */
    .dismiss-btn {
      width: auto;
      min-width: 44px;
      min-height: 44px;
      padding: 8px 10px;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 6px;
    }

    .dismiss-label {
      display: inline;
      font-size: var(--autodoc-meta-size);
    }

    .issue-icon {
      font-size: 0.75rem;
    }

    .edit-link {
      margin-left: 16px;
      min-height: 44px;
      display: inline-flex;
      align-items: center;
    }

    .fix-suggestion {
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-sm);
      flex-wrap: wrap;
    }

    .copy-fix-btn,
    .apply-fix-btn {
      min-height: 36px;
      padding: 6px 10px;
    }
  }
`;
/**
 * Card layout styles: ha-card shell, header, tabs, content area,
 * loading/error/empty/healthy states, footer with run button.
 */
const cardLayoutStyles = i$3 `
  ha-card {
    overflow: hidden;
    width: 100%;
    box-sizing: border-box;
    position: relative;
  }

  /* Header */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--autodoc-spacing-lg);
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .title {
    margin: 0;
    font-size: var(--autodoc-title-size);
    font-weight: 600;
    color: var(--primary-text-color);
  }

  /* Card content */
  .card-content {
    padding: var(--autodoc-spacing-lg);
  }

  /* Loading state */
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
    gap: var(--autodoc-spacing-md);
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--divider-color, rgba(127, 127, 127, 0.3));
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-issue-size);
  }

  /* Error state */
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
    gap: var(--autodoc-spacing-md);
    text-align: center;
  }

  .error-icon {
    font-size: 2rem;
    color: var(--autodoc-error);
  }

  .error-text {
    color: var(--autodoc-error);
    font-size: var(--autodoc-issue-size);
  }

  .retry-btn {
    margin-top: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
    background: transparent;
    color: var(--primary-color);
    border: 1px solid var(--primary-color);
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    cursor: pointer;
    transition:
      background var(--autodoc-transition-fast),
      color var(--autodoc-transition-fast);
  }

  .retry-btn:hover {
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
  }

  /* Empty state */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--autodoc-spacing-xl);
  }

  .empty-text {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-issue-size);
  }

  /* All healthy state */
  .all-healthy {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    padding: var(--autodoc-spacing-lg);
    background: rgba(46, 139, 87, 0.08);
    border-radius: 8px;
  }

  .healthy-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
    border-radius: 50%;
    font-size: 1.25rem;
    font-weight: bold;
  }

  .healthy-message {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .healthy-title {
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--autodoc-success);
  }

  .healthy-subtitle {
    font-size: var(--autodoc-meta-size);
    color: var(--secondary-text-color);
  }

  /* Footer */
  .footer {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
    border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
  }

  .run-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
    border: none;
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    font-weight: 500;
    cursor: pointer;
    transition:
      opacity var(--autodoc-transition-fast),
      transform var(--autodoc-transition-fast);
  }

  .run-btn:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
  }

  .run-btn:focus {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }

  .run-btn:disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }

  .undo-btn {
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
    border-radius: 6px;
    background: transparent;
    color: var(--secondary-text-color);
    font-size: var(--autodoc-meta-size);
    cursor: pointer;
    transition: background var(--autodoc-transition-fast);
  }

  .undo-btn:hover {
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
  }

  .run-icon {
    font-size: 0.8rem;
  }

  .run-btn.running .run-icon {
    animation: spin 1s linear infinite;
  }

  .last-run {
    color: var(--secondary-text-color);
    font-size: var(--autodoc-meta-size);
  }

  /* Mobile responsive */
  @media (max-width: 600px) {
    .card-content {
      padding: var(--autodoc-spacing-md);
    }

    .header {
      padding: var(--autodoc-spacing-md);
    }

    .footer {
      padding: var(--autodoc-spacing-md);
      flex-wrap: wrap;
    }

    .run-btn {
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
      font-size: var(--autodoc-name-size);
      min-height: 44px;
    }

    .undo-btn {
      min-height: 44px;
      font-size: var(--autodoc-issue-size);
    }

    .run-icon {
      font-size: 0.9rem;
    }

    .retry-btn {
      min-height: 44px;
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-xl);
      font-size: var(--autodoc-name-size);
    }
  }

  /* Toast notification */
  .toast {
    position: absolute;
    bottom: 60px;
    left: 50%;
    transform: translateX(-50%) translateY(8px);
    background: var(--primary-text-color);
    color: var(--card-background-color, #fff);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--autodoc-transition-normal), transform var(--autodoc-transition-normal);
    z-index: 10;
    white-space: nowrap;
  }

  .toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }

`;
/**
 * Pipeline styles: validation group panels with neutral/active/result states,
 * JS-driven stagger transitions, summary rollup bar, and
 * three-state (pass/warning/fail) visual treatment.
 */
const pipelineStyles = i$3 `
  .pipeline {
    display: flex;
    flex-direction: column;
    gap: var(--autodoc-spacing-sm);
    margin-bottom: var(--autodoc-spacing-lg);
  }

  /* Individual group panel -- JS controls visibility via state classes */
  .pipeline-group {
    display: flex;
    align-items: center;
    padding: var(--autodoc-spacing-md);
    border-radius: 8px;
    background: rgba(127, 127, 127, 0.06);
    border-left: 3px solid transparent;
    opacity: 1;
    transition: opacity 200ms ease, border-color 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
  }

  /* Neutral: dimmed "waiting" state before this group is checked */
  .pipeline-group.neutral {
    opacity: 0.45;
    border-left-color: transparent;
    background: rgba(127, 127, 127, 0.04);
  }

  /* Active: highlighted state -- the primary running indicator */
  .pipeline-group.active {
    opacity: 1;
    border-left: 3px solid var(--primary-color);
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
    box-shadow: 0 0 0 1px rgba(var(--rgb-primary-color, 66, 133, 244), 0.15);
  }

  /* Status-specific left border (result states) */
  .pipeline-group.pass {
    border-left: 3px solid var(--autodoc-success);
  }
  .pipeline-group.warning {
    border-left: 3px solid var(--autodoc-warning);
  }
  .pipeline-group.fail {
    border-left: 3px solid var(--autodoc-error);
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-md);
    width: 100%;
  }

  /* Status icon circle */
  .group-status-icon {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 0.85rem;
    font-weight: bold;
    flex-shrink: 0;
  }

  .pipeline-group.active .group-status-icon {
    background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.15);
    color: var(--primary-color);
  }

  .pipeline-group.pass .group-status-icon {
    background: rgba(46, 139, 87, 0.15);
    color: var(--autodoc-success);
  }
  .pipeline-group.warning .group-status-icon {
    background: rgba(196, 144, 8, 0.15);
    color: var(--autodoc-warning);
  }
  .pipeline-group.fail .group-status-icon {
    background: rgba(217, 72, 72, 0.15);
    color: var(--autodoc-error);
  }

  /* Active dot indicator (replaces spinner) */
  .active-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary-color);
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.75); }
  }

  .group-label {
    flex: 1;
    font-size: var(--autodoc-name-size);
    font-weight: 600;
    color: var(--primary-text-color);
  }

  .group-count {
    font-size: var(--autodoc-meta-size);
    font-weight: 500;
  }
  .group-count.pass-text { color: var(--autodoc-success); }
  .group-count.warning-text { color: var(--autodoc-warning); }
  .group-count.fail-text { color: var(--autodoc-error); }

  /* Summary rollup bar -- visibility controlled by JS _showSummary */
  .pipeline-summary {
    display: flex;
    align-items: center;
    gap: var(--autodoc-spacing-sm);
    padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    border-radius: 6px;
    font-size: var(--autodoc-issue-size);
    font-weight: 500;
    opacity: 1;
    transition: opacity 200ms ease;
  }

  .pipeline-summary.pass {
    background: rgba(46, 139, 87, 0.08);
    color: var(--autodoc-success);
  }
  .pipeline-summary.warning {
    background: rgba(196, 144, 8, 0.08);
    color: var(--autodoc-warning);
  }
  .pipeline-summary.fail {
    background: rgba(217, 72, 72, 0.08);
    color: var(--autodoc-error);
  }

  /* Respect reduced motion -- CSS layer (JS layer skips stagger loop separately) */
  @media (prefers-reduced-motion: reduce) {
    .pipeline-group,
    .pipeline-summary {
      transition: none;
    }
    .active-dot {
      animation: none;
    }
  }
`;

/**
 * Render the badge row for the validation tab.
 * Shows error, warning, healthy, and suppressed counts.
 *
 * When in suppressions view, clicking any issue badge navigates back to issues.
 * The suppressed badge toggles between views.
 *
 * @param counts - Issue/status counts to display
 * @param onNavigate - Optional callback for navigation (e.g. to suppressions view)
 * @param activeView - Current active view ("issues" or "suppressions")
 */
function renderBadges(counts, onNavigate, activeView) {
    const inSuppressions = activeView === "suppressions";
    const goToIssues = inSuppressions ? () => onNavigate?.("issues") : A;
    const navStyle = inSuppressions ? "cursor: pointer;" : "";
    return b `
    <div class="badges-row">
      ${counts.errors > 0
        ? b `<span
            class="badge badge-error"
            title="${counts.errors} error${counts.errors !== 1 ? "s" : ""}"
            style=${navStyle}
            @click=${goToIssues}
          >
            <span class="badge-icon" aria-hidden="true">\u2715</span>
            <span class="badge-count">${counts.errors}</span>
          </span>`
        : A}
      ${counts.warnings > 0
        ? b `<span
            class="badge badge-warning"
            title="${counts.warnings} warning${counts.warnings !== 1 ? "s" : ""}"
            style=${navStyle}
            @click=${goToIssues}
          >
            <span class="badge-icon" aria-hidden="true">!</span>
            <span class="badge-count">${counts.warnings}</span>
          </span>`
        : A}
      ${counts.healthy > 0
        ? b `<span
            class="badge badge-healthy"
            title="${counts.healthy} healthy"
            style=${navStyle}
            @click=${goToIssues}
          >
            <span class="badge-icon" aria-hidden="true">\u2713</span>
            <span class="badge-count">${counts.healthy}</span>
          </span>`
        : A}
      ${counts.suppressed > 0
        ? b `<span
            class="badge badge-suppressed ${inSuppressions ? "badge-active" : ""}"
            title="${counts.suppressed} suppressed"
            role="button"
            tabindex="0"
            @click=${() => onNavigate?.(inSuppressions ? "issues" : "suppressions")}
            @keydown=${(e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onNavigate?.(inSuppressions ? "issues" : "suppressions");
            }
        }}
            style="cursor: pointer;"
          >
            <span class="badge-icon" aria-hidden="true">\u2298</span>
            <span class="badge-count">${counts.suppressed}</span>
          </span>`
        : A}
    </div>
  `;
}

/**
 * Renders a single automation group with its issues, fix suggestions,
 * confidence pills, and action buttons (suppress/dismiss).
 *
 * Data flows DOWN via properties; actions flow UP via CustomEvents.
 */
let AutodocIssueGroup = class AutodocIssueGroup extends i {
    constructor() {
        super(...arguments);
        this.dismissedKeys = new Set();
    }
    render() {
        const group = this.group;
        return b `
      <div class="automation-group ${group.has_error ? "has-error" : "has-warning"}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true"
            >${group.has_error ? "\u2715" : "!"}</span
          >
          <span class="automation-name" title="${group.automation_name}">${group.automation_name}</span>
          <span class="automation-badge">${group.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${group.issues.map((item) => this._renderIssue(item))}
        </div>
        ${group.edit_url
            ? b `
              <a href="${group.edit_url}" class="edit-link" aria-label="Edit ${group.automation_name}">
                <span class="edit-text">Edit automation</span>
                <span class="edit-arrow" aria-hidden="true">\u2192</span>
              </a>
            `
            : A}
      </div>
    `;
    }
    _renderIssue(item) {
        const { issue, fix } = item;
        const isError = issue.severity === "error";
        const isDismissed = this.dismissedKeys.has(getSuggestionKey(issue));
        return b `
      <div class="issue ${isError ? "error" : "warning"}">
        <div class="issue-header">
          <span class="issue-icon" aria-hidden="true">${isError ? "\u2715" : "!"}</span>
          <span class="issue-message">${issue.message}</span>
          <button
            class="suppress-btn"
            @click=${() => this._dispatchSuppress(issue)}
            aria-label="Suppress this issue"
            title="Don't show this issue again"
          >
            <span aria-hidden="true">\u2298</span><span class="suppress-label">Suppress</span>
          </button>
        </div>
        ${fix && !isDismissed
            ? b `
              <div class="fix-suggestion">
                <ha-icon class="fix-icon" icon="mdi:lightbulb-on-outline" style="--mdc-icon-size: 16px; color: var(--primary-color);" aria-hidden="true"></ha-icon>
                <div class="fix-content">
                  <span class="fix-description">${fix.description}</span>
                  ${this._renderFixReplacement(fix)}
                  ${fix.reason ? b `<span class="fix-reason">${fix.reason}</span>` : A}
                  ${this._renderConfidencePill(fix.confidence)}
                </div>
                <div class="fix-actions">
                  ${fix.suggested_value || fix.fix_value
                ? b `
                        <button
                          class="copy-fix-btn"
                          @click=${() => this._copyFixValue(fix)}
                          aria-label="Copy suggested value"
                        >
                          Copy
                        </button>
                      `
                : A}
                  ${this._canApplyFix(issue, fix)
                ? b `
                        <button
                          class="apply-fix-btn"
                          @click=${() => this._dispatchApply(issue, fix)}
                          aria-label="Apply suggestion"
                        >
                          Apply
                        </button>
                      `
                : A}
                </div>
                <button
                  class="dismiss-btn"
                  @click=${() => this._dispatchDismiss(issue)}
                  aria-label="Dismiss suggestion"
                >
                  <span aria-hidden="true">\u2715</span><span class="dismiss-label">Dismiss</span>
                </button>
              </div>
            `
            : A}
      </div>
    `;
    }
    _renderFixReplacement(fix) {
        if (fix.fix_type !== "replace_value" ||
            !fix.current_value ||
            !(fix.suggested_value || fix.fix_value)) {
            return A;
        }
        const suggested = fix.suggested_value || fix.fix_value || "";
        return b `
      <span class="fix-replacement">
        <code class="fix-before">${fix.current_value}</code>
        <span class="fix-arrow" aria-hidden="true">\u2192</span>
        <code class="fix-after">${suggested}</code>
      </span>
    `;
    }
    _renderConfidencePill(confidence) {
        if (confidence <= 0.6) {
            return A;
        }
        const isHigh = confidence > 0.9;
        return b `
      <span class="confidence-pill ${isHigh ? "high" : "medium"}">
        ${isHigh ? "High" : "Medium"} confidence
      </span>
    `;
    }
    _dispatchSuppress(issue) {
        this.dispatchEvent(new CustomEvent("suppress-issue", {
            detail: { issue },
            bubbles: true,
            composed: true,
        }));
    }
    _dispatchDismiss(issue) {
        this.dispatchEvent(new CustomEvent("dismiss-suggestion", {
            detail: { issue },
            bubbles: true,
            composed: true,
        }));
    }
    _canApplyFix(issue, fix) {
        return (fix.fix_type === "replace_value" &&
            !!fix.suggested_value &&
            !!issue.location &&
            confidenceAtLeast(fix.confidence, 0.8));
    }
    async _copyFixValue(fix) {
        const value = fix.suggested_value || fix.fix_value;
        if (!value || !navigator.clipboard?.writeText) {
            return;
        }
        await navigator.clipboard.writeText(value);
        this.dispatchEvent(new CustomEvent("fix-copied", {
            detail: { value },
            bubbles: true,
            composed: true,
        }));
    }
    _dispatchApply(issue, fix) {
        this.dispatchEvent(new CustomEvent("apply-fix", {
            detail: { issue, fix },
            bubbles: true,
            composed: true,
        }));
    }
};
AutodocIssueGroup.styles = [autodocTokens, issueGroupStyles];
__decorate([
    n({ attribute: false })
], AutodocIssueGroup.prototype, "group", void 0);
__decorate([
    n({ attribute: false })
], AutodocIssueGroup.prototype, "dismissedKeys", void 0);
AutodocIssueGroup = __decorate([
    t("autodoc-issue-group")
], AutodocIssueGroup);
function confidenceAtLeast(actual, min) {
    return typeof actual === "number" && actual >= min;
}

/** How long the accent highlight stays on each group (ms). */
const ACTIVE_DURATION_MS = 300;
/** Gap between one group resolving and the next group highlighting (ms). */
const INTER_GROUP_DELAY_MS = 100;
let AutodocPipeline = class AutodocPipeline extends i {
    constructor() {
        super(...arguments);
        this.groups = [];
        this.running = false;
        /** Per-group display state: "neutral", "active", "pass", "warning", or "fail". */
        this._displayStates = [];
        /** Controls summary rollup visibility. */
        this._showSummary = false;
        /** Monotonically increasing ID for abort guard. */
        this._staggerRunId = 0;
    }
    disconnectedCallback() {
        super.disconnectedCallback();
        // Cancel any pending stagger by invalidating the current run ID
        this._staggerRunId++;
    }
    updated(changedProps) {
        super.updated(changedProps);
        if (changedProps.has("running")) {
            const prevRunning = changedProps.get("running");
            if (this.running) {
                // Validation just started: reset to neutral, hide summary
                this._displayStates = this.groups.map(() => "neutral");
                this._showSummary = false;
            }
            else if (prevRunning === true && !this.running && this.groups.length > 0) {
                // Validation just finished: start stagger sequence
                this._startStagger();
            }
        }
    }
    async _startStagger() {
        const runId = ++this._staggerRunId;
        // Reduced motion: skip animation entirely, show all results at once
        if (this._prefersReducedMotion()) {
            this._displayStates = this.groups.map((g) => g.status);
            this._showSummary = true;
            return;
        }
        // Initialize all groups to neutral
        this._displayStates = this.groups.map(() => "neutral");
        this._showSummary = false;
        for (let i = 0; i < this.groups.length; i++) {
            // Abort guard: another stagger started or component disconnected
            if (this._staggerRunId !== runId)
                return;
            // Highlight current group
            this._displayStates = [...this._displayStates];
            this._displayStates[i] = "active";
            this.requestUpdate();
            await this._delay(ACTIVE_DURATION_MS);
            // Abort guard after delay
            if (this._staggerRunId !== runId)
                return;
            // Resolve current group to its final status
            this._displayStates = [...this._displayStates];
            this._displayStates[i] = this.groups[i].status;
            // Show summary simultaneously with last group resolving
            if (i === this.groups.length - 1) {
                this._showSummary = true;
            }
            this.requestUpdate();
            // Inter-group delay (skip after last group)
            if (i < this.groups.length - 1) {
                await this._delay(INTER_GROUP_DELAY_MS);
            }
        }
    }
    _delay(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
    _prefersReducedMotion() {
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }
    render() {
        return b `
      <div class="pipeline" role="region" aria-label="Validation pipeline">
        ${this.groups.map((group, i) => this._renderGroup(group, i))}
        ${this._showSummary
            ? this._renderSummary()
            : A}
      </div>
    `;
    }
    _renderGroup(group, index) {
        const displayState = this._displayStates[index] ?? group.status;
        const isResult = displayState !== "neutral" && displayState !== "active";
        return b `
      <div class="pipeline-group ${displayState}">
        <div class="group-header">
          <div class="group-status-icon" aria-hidden="true">
            ${displayState === "active"
            ? b `<span class="active-dot"></span>`
            : isResult
                ? this._statusIcon(displayState)
                : A}
          </div>
          <span class="group-label">${group.label}</span>
          ${isResult ? this._renderCounts(group) : A}
        </div>
      </div>
    `;
    }
    _statusIcon(status) {
        const icons = {
            pass: "\u2713",
            warning: "!",
            fail: "\u2715",
        };
        return b `<span>${icons[status] || "?"}</span>`;
    }
    _renderCounts(group) {
        if (group.issue_count === 0) {
            return b `<span class="group-count pass-text">No issues</span>`;
        }
        const parts = [];
        if (group.error_count > 0) {
            parts.push(`${group.error_count} error${group.error_count !== 1 ? "s" : ""}`);
        }
        if (group.warning_count > 0) {
            parts.push(`${group.warning_count} warning${group.warning_count !== 1 ? "s" : ""}`);
        }
        return b `<span class="group-count ${group.status}-text">${parts.join(", ")}</span>`;
    }
    _getOverallStatus() {
        if (this.groups.some((g) => g.status === "fail"))
            return "fail";
        if (this.groups.some((g) => g.status === "warning"))
            return "warning";
        return "pass";
    }
    _renderSummary() {
        const status = this._getOverallStatus();
        const totalErrors = this.groups.reduce((sum, g) => sum + g.error_count, 0);
        const totalWarnings = this.groups.reduce((sum, g) => sum + g.warning_count, 0);
        const messages = {
            pass: "All checks passed",
            warning: `${totalWarnings} warning${totalWarnings !== 1 ? "s" : ""} found`,
            fail: `${totalErrors} error${totalErrors !== 1 ? "s" : ""}${totalWarnings > 0 ? `, ${totalWarnings} warning${totalWarnings !== 1 ? "s" : ""}` : ""} found`,
        };
        return b `
      <div
        class="pipeline-summary ${status}"
        role="status"
      >
        <span class="summary-icon" aria-hidden="true">${this._statusIcon(status)}</span>
        <span class="summary-text">${messages[status]}</span>
      </div>
    `;
    }
};
AutodocPipeline.styles = [autodocTokens, pipelineStyles];
__decorate([
    n({ attribute: false })
], AutodocPipeline.prototype, "groups", void 0);
__decorate([
    n({ type: Boolean })
], AutodocPipeline.prototype, "running", void 0);
__decorate([
    r()
], AutodocPipeline.prototype, "_displayStates", void 0);
__decorate([
    r()
], AutodocPipeline.prototype, "_showSummary", void 0);
AutodocPipeline = __decorate([
    t("autodoc-pipeline")
], AutodocPipeline);

let AutodocSuppressions = class AutodocSuppressions extends i {
    constructor() {
        super(...arguments);
        this._suppressions = [];
        this._loading = true;
        this._error = null;
        this._confirmingClearAll = false;
    }
    connectedCallback() {
        super.connectedCallback();
        this._fetchSuppressions();
    }
    async _fetchSuppressions() {
        this._loading = true;
        this._error = null;
        try {
            const resp = await this.hass.callWS({
                type: "autodoctor/list_suppressions",
            });
            this._suppressions = resp.suppressions;
        }
        catch (err) {
            console.error("Failed to fetch suppressions:", err);
            this._error = "Failed to load suppressions";
        }
        this._loading = false;
    }
    async _unsuppress(key) {
        try {
            await this.hass.callWS({
                type: "autodoctor/unsuppress",
                key,
            });
            this._suppressions = this._suppressions.filter((s) => s.key !== key);
            this.dispatchEvent(new CustomEvent("suppressions-changed", {
                detail: { action: "restore" },
                bubbles: true,
                composed: true,
            }));
        }
        catch (err) {
            console.error("Failed to unsuppress:", err);
        }
    }
    async _clearAll() {
        try {
            await this.hass.callWS({ type: "autodoctor/clear_suppressions" });
            this._suppressions = [];
            this.dispatchEvent(new CustomEvent("suppressions-changed", {
                detail: { action: "clear-all" },
                bubbles: true,
                composed: true,
            }));
        }
        catch (err) {
            console.error("Failed to clear suppressions:", err);
        }
    }
    _confirmClearAll() {
        if (this._confirmTimeout) {
            clearTimeout(this._confirmTimeout);
            this._confirmTimeout = undefined;
        }
        this._confirmingClearAll = false;
        this._clearAll();
    }
    _startConfirmClearAll() {
        this._confirmingClearAll = true;
        if (this._confirmTimeout) {
            clearTimeout(this._confirmTimeout);
        }
        this._confirmTimeout = setTimeout(() => {
            this._confirmingClearAll = false;
        }, 5000);
    }
    _cancelConfirmClearAll() {
        if (this._confirmTimeout) {
            clearTimeout(this._confirmTimeout);
            this._confirmTimeout = undefined;
        }
        this._confirmingClearAll = false;
    }
    render() {
        if (this._loading) {
            return b `<div class="loading">Loading suppressions...</div>`;
        }
        if (this._error) {
            return b `<div class="error">${this._error}</div>`;
        }
        if (this._suppressions.length === 0) {
            return b `<div class="empty">No suppressed issues</div>`;
        }
        return b `
      <div class="suppressions-list">
        <div class="suppressions-header">
          <span class="suppressions-title"
            >${this._suppressions.length} suppressed
            issue${this._suppressions.length !== 1 ? "s" : ""}</span
          >
          ${this._confirmingClearAll
            ? b `<span class="confirm-prompt">
                <span class="confirm-text">Are you sure?</span>
                <button class="confirm-yes-btn" @click=${() => this._confirmClearAll()}>Yes</button>
                <button class="confirm-cancel-btn" @click=${() => this._cancelConfirmClearAll()}>Cancel</button>
              </span>`
            : b `<button class="clear-all-btn" @click=${() => this._startConfirmClearAll()}>Clear all</button>`}
        </div>
        ${this._suppressions.map((s) => this._renderSuppression(s))}
      </div>
    `;
    }
    _renderSuppression(entry) {
        return b `
      <div class="suppression-item">
        <div class="suppression-info">
          <span class="suppression-automation" title="${entry.automation_name || entry.automation_id}"
            >${entry.automation_name || entry.automation_id}</span
          >
          <span class="suppression-detail" title="${entry.entity_id}${entry.message ? ` \u2014 ${entry.message}` : ""}"
            >${entry.entity_id}${entry.message ? ` \u2014 ${entry.message}` : ""}</span
          >
        </div>
        <button
          class="restore-btn"
          @click=${() => this._unsuppress(entry.key)}
          title="Restore this issue"
          aria-label="Restore suppressed issue"
        >
          <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size: 18px;"></ha-icon>
        </button>
      </div>
    `;
    }
    static get styles() {
        return [
            autodocTokens,
            i$3 `
        :host {
          display: block;
        }

        .loading,
        .error,
        .empty {
          padding: var(--autodoc-spacing-lg);
          text-align: center;
          color: var(--secondary-text-color);
          font-size: var(--autodoc-issue-size);
        }

        .error {
          color: var(--autodoc-error);
        }

        .suppressions-list {
          display: flex;
          flex-direction: column;
          gap: var(--autodoc-spacing-sm);
        }

        .suppressions-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0 0 var(--autodoc-spacing-sm) 0;
        }

        .suppressions-title {
          font-size: var(--autodoc-name-size);
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .clear-all-btn {
          background: transparent;
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          border-radius: 6px;
          color: var(--primary-color);
          font-size: var(--autodoc-meta-size);
          padding: 4px 10px;
          cursor: pointer;
          transition: background var(--autodoc-transition-fast);
        }

        .clear-all-btn:hover {
          background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.08);
        }

        .suppression-item {
          display: flex;
          align-items: center;
          gap: var(--autodoc-spacing-sm);
          padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
          background: rgba(127, 127, 127, 0.06);
          border-radius: 8px;
          border-left: 3px solid var(--secondary-text-color);
        }

        .suppression-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 2px;
          overflow: hidden;
        }

        .suppression-automation {
          font-size: var(--autodoc-name-size);
          font-weight: 500;
          color: var(--primary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .suppression-detail {
          font-size: var(--autodoc-meta-size);
          color: var(--secondary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .restore-btn {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          padding: 0;
          background: transparent;
          border: none;
          border-radius: 50%;
          color: var(--secondary-text-color);
          cursor: pointer;
          transition:
            background var(--autodoc-transition-fast),
            color var(--autodoc-transition-fast);
        }

        .restore-btn:hover {
          background: rgba(var(--rgb-primary-color, 66, 133, 244), 0.1);
          color: var(--primary-color);
        }

        .confirm-prompt {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: var(--autodoc-meta-size);
        }

        .confirm-text {
          color: var(--secondary-text-color);
          font-weight: 500;
        }

        .confirm-yes-btn,
        .confirm-cancel-btn {
          background: transparent;
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          border-radius: 4px;
          padding: 2px 8px;
          cursor: pointer;
          font-size: var(--autodoc-meta-size);
          transition: background var(--autodoc-transition-fast);
        }

        .confirm-yes-btn {
          color: var(--autodoc-error);
          border-color: var(--autodoc-error);
        }

        .confirm-yes-btn:hover {
          background: rgba(217, 72, 72, 0.1);
        }

        .confirm-cancel-btn {
          color: var(--secondary-text-color);
        }

        .confirm-cancel-btn:hover {
          background: rgba(127, 127, 127, 0.1);
        }

        /* Mobile: touch-friendly suppressions */
        @media (max-width: 600px) {
          .restore-btn {
            width: 44px;
            height: 44px;
          }

          .clear-all-btn {
            min-height: 44px;
            padding: 8px 14px;
            font-size: var(--autodoc-issue-size);
          }

          .suppression-item {
            padding: var(--autodoc-spacing-md);
          }
        }
      `,
        ];
    }
};
__decorate([
    n({ attribute: false })
], AutodocSuppressions.prototype, "hass", void 0);
__decorate([
    r()
], AutodocSuppressions.prototype, "_suppressions", void 0);
__decorate([
    r()
], AutodocSuppressions.prototype, "_loading", void 0);
__decorate([
    r()
], AutodocSuppressions.prototype, "_error", void 0);
__decorate([
    r()
], AutodocSuppressions.prototype, "_confirmingClearAll", void 0);
AutodocSuppressions = __decorate([
    t("autodoc-suppressions")
], AutodocSuppressions);

var AutodoctorCard_1;
const CARD_VERSION = "2.23.3";
console.info(`%c AUTODOCTOR-CARD %c ${CARD_VERSION} `, "color: white; background: #3498db; font-weight: bold;", "color: #3498db; background: white; font-weight: bold;");
let AutodoctorCard = AutodoctorCard_1 = class AutodoctorCard extends i {
    constructor() {
        super(...arguments);
        this._loading = true;
        this._error = null;
        this._validationData = null;
        this._runningValidation = false;
        this._dismissedSuggestions = new Set();
        this._view = "issues";
        this._toastMessage = "";
        this._toastVisible = false;
        this._cooldownUntil = 0;
        this._canUndoLastFix = false;
        // Request tracking to prevent race conditions
        this._validationRequestId = 0;
        this._suppressionInProgress = false;
    }
    setConfig(config) {
        this.config = config;
    }
    static getStubConfig() {
        return {
            type: "custom:autodoctor-card",
        };
    }
    static async getConfigElement() {
        await Promise.resolve().then(function () { return autodoctorCardEditor; });
        return document.createElement("autodoctor-card-editor");
    }
    async firstUpdated() {
        await this._fetchValidation();
        this._startAutoRefresh();
    }
    async _fetchValidation(showLoading = true) {
        // Increment request ID to track this specific request
        const requestId = ++this._validationRequestId;
        if (showLoading) {
            this._loading = true;
        }
        try {
            this._error = null;
            const data = await this.hass.callWS({
                type: "autodoctor/validation/steps",
            });
            // Only update state if this is still the latest request
            if (requestId === this._validationRequestId) {
                this._validationData = data;
            }
        }
        catch (err) {
            // Only set error if this is still the latest request
            if (requestId === this._validationRequestId) {
                console.error("Failed to fetch validation data:", err);
                this._error = "Failed to load validation data";
            }
        }
        // Only clear loading if this is still the latest request
        if (requestId === this._validationRequestId && showLoading) {
            this._loading = false;
        }
    }
    _startAutoRefresh() {
        if (this._autoRefreshTimer) {
            return;
        }
        this._autoRefreshTimer = setInterval(() => {
            // Skip while a foreground action is in progress.
            if (this._runningValidation || this._loading || !this.isConnected) {
                return;
            }
            void this._fetchValidation(false);
        }, AutodoctorCard_1.AUTO_REFRESH_MS);
    }
    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._cooldownTimeout) {
            clearTimeout(this._cooldownTimeout);
            this._cooldownTimeout = undefined;
        }
        if (this._toastTimeout) {
            clearTimeout(this._toastTimeout);
            this._toastTimeout = undefined;
        }
        if (this._autoRefreshTimer) {
            clearInterval(this._autoRefreshTimer);
            this._autoRefreshTimer = undefined;
        }
    }
    _startCooldown() {
        this._cooldownUntil = Date.now() + AutodoctorCard_1.CLICK_COOLDOWN_MS;
        if (this._cooldownTimeout) {
            clearTimeout(this._cooldownTimeout);
        }
        this._cooldownTimeout = setTimeout(() => {
            this._cooldownUntil = 0;
            this._cooldownTimeout = undefined;
        }, AutodoctorCard_1.CLICK_COOLDOWN_MS + 10);
    }
    async _runValidation() {
        // Prevent concurrent runs and enforce cooldown
        const now = Date.now();
        if (this._runningValidation ||
            this._cooldownUntil > now) {
            return;
        }
        this._startCooldown();
        const requestId = ++this._validationRequestId;
        this._runningValidation = true;
        try {
            const data = await this.hass.callWS({
                type: "autodoctor/validation/run_steps",
            });
            // Only update state if this is still the latest request
            if (requestId === this._validationRequestId) {
                this._validationData = data;
            }
        }
        catch (err) {
            if (requestId === this._validationRequestId) {
                console.error("Failed to run validation:", err);
            }
        }
        // Only clear running flag if this is still the latest request
        if (requestId === this._validationRequestId) {
            this._runningValidation = false;
        }
    }
    _groupIssuesByAutomation(issues) {
        const groups = new Map();
        for (const item of issues) {
            const { issue, edit_url } = item;
            const key = issue.automation_id;
            if (!groups.has(key)) {
                groups.set(key, {
                    automation_id: issue.automation_id,
                    automation_name: issue.automation_name,
                    issues: [],
                    edit_url,
                    has_error: false,
                    error_count: 0,
                    warning_count: 0,
                });
            }
            const group = groups.get(key);
            group.issues.push(item);
            if (issue.severity === "error") {
                group.has_error = true;
                group.error_count++;
            }
            else {
                group.warning_count++;
            }
        }
        return Array.from(groups.values());
    }
    _getCounts(data) {
        if (!data) {
            return { errors: 0, warnings: 0, healthy: 0, suppressed: 0 };
        }
        let errors = 0;
        let warnings = 0;
        for (const item of data.issues) {
            if (item.issue.severity === "error") {
                errors++;
            }
            else {
                warnings++;
            }
        }
        return {
            errors,
            warnings,
            healthy: data.healthy_count,
            suppressed: data.suppressed_count || 0,
        };
    }
    render() {
        const title = this.config.title || "Autodoctor";
        if (this._loading) {
            return this._renderLoading(title);
        }
        if (this._error) {
            return this._renderError(title);
        }
        const data = this._validationData;
        if (!data) {
            return this._renderEmpty(title);
        }
        const groups = this._groupIssuesByAutomation(data.issues);
        const counts = this._getCounts(data);
        const hasIssues = data.issues.length > 0;
        const hasRun = !!data.last_run;
        return b `
      <ha-card>
        ${this._renderHeader(title)}
        <div class="card-content">
          ${this._renderBadges(counts)}
          ${hasRun
            ? b `<autodoc-pipeline
                .groups=${data.groups || []}
                ?running=${this._runningValidation}
              ></autodoc-pipeline>`
            : A}
          ${this._view === "suppressions"
            ? b `<autodoc-suppressions
                .hass=${this.hass}
                @suppressions-changed=${(e) => this._onSuppressionsChanged(e.detail?.action)}
              ></autodoc-suppressions>`
            : hasIssues
                ? groups.map((group) => b `
                    <autodoc-issue-group
                      .group=${group}
                      .dismissedKeys=${this._dismissedSuggestions}
                      @suppress-issue=${(e) => this._suppressIssue(e.detail.issue)}
                      @dismiss-suggestion=${(e) => this._dismissSuggestion(e.detail.issue)}
                      @fix-copied=${(e) => this._showToast(`Copied: ${e.detail.value}`)}
                      @apply-fix=${(e) => this._applyFix(e.detail.issue, e.detail.fix)}
                    ></autodoc-issue-group>
                  `)
                : hasRun
                    ? this._renderAllHealthy(counts.healthy, data.analyzed_automations ?? counts.healthy)
                    : this._renderFirstRun()}
        </div>
        ${this._renderFooter()}
        <div class="toast ${this._toastVisible ? 'show' : ''}">${this._toastMessage}</div>
      </ha-card>
    `;
    }
    _renderLoading(title) {
        return b `
      <ha-card>
        <div class="header">
          <h2 class="title">${title}</h2>
        </div>
        <div class="card-content loading-state">
          <div class="spinner" aria-label="Loading"></div>
          <span class="loading-text">Checking automations...</span>
        </div>
      </ha-card>
    `;
    }
    _renderError(title) {
        return b `
      <ha-card>
        <div class="header">
          <h2 class="title">${title}</h2>
        </div>
        <div class="card-content error-state">
          <div class="error-icon" aria-hidden="true">\u26A0</div>
          <span class="error-text">${this._error}</span>
          <button class="retry-btn" @click=${() => this._fetchValidation()}>Try again</button>
        </div>
      </ha-card>
    `;
    }
    _renderEmpty(title) {
        return b `
      <ha-card>
        ${this._renderHeader(title)}
        <div class="card-content empty-state">
          <span class="empty-text">No data available</span>
        </div>
      </ha-card>
    `;
    }
    _renderHeader(title) {
        return b `
      <div class="header">
        <h2 class="title">${title}</h2>
      </div>
    `;
    }
    _renderAllHealthy(healthyCount, analyzedCount) {
        return b `
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">\u2713</div>
        <div class="healthy-message">
          <span class="healthy-title">All systems healthy</span>
          <span class="healthy-subtitle"
            >${analyzedCount} automation${analyzedCount !== 1 ? "s" : ""} analyzed</span
          >
        </div>
      </div>
    `;
    }
    _renderFirstRun() {
        return b `
      <div class="empty-state">
        <span class="empty-text">Click "Run Validation" to scan your automations</span>
      </div>
    `;
    }
    _renderBadges(counts) {
        return renderBadges(counts, (view) => {
            this._view = view;
        }, this._view);
    }
    _renderFooter() {
        // Disable button during any async operation or cooldown period
        const isRunning = this._runningValidation || this._loading;
        const isDisabled = isRunning || this._cooldownUntil > Date.now();
        return b `
      <div class="footer">
        <button
          class="run-btn ${isRunning ? "running" : ""}"
          @click=${() => this._runValidation()}
          ?disabled=${isDisabled}
        >
          <span class="run-icon" aria-hidden="true">${isRunning ? "\u21BB" : "\u25B6"}</span>
          <span class="run-text">${isRunning ? "Running..." : isDisabled ? "Please wait..." : "Run Validation"}</span>
        </button>
        ${this._canUndoLastFix
            ? b `
              <button class="undo-btn" @click=${() => this._undoLastFix()}>
                Undo last fix
              </button>
            `
            : A}
        ${this._validationData?.last_run
            ? b ` <span class="last-run"
              >Last run: ${this._formatLastRun(this._validationData.last_run)}</span
            >`
            : A}
      </div>
    `;
    }
    _formatLastRun(isoString) {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1)
            return "just now";
        if (diffMins < 60)
            return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24)
            return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        return `${diffDays}d ago`;
    }
    _dismissSuggestion(issue) {
        const key = getSuggestionKey(issue);
        this._dismissedSuggestions = new Set([...this._dismissedSuggestions, key]);
    }
    async _suppressIssue(issue) {
        // Prevent concurrent suppression operations
        if (this._suppressionInProgress) {
            return;
        }
        this._suppressionInProgress = true;
        try {
            await this.hass.callWS({
                type: "autodoctor/suppress",
                automation_id: issue.automation_id,
                entity_id: issue.entity_id,
                issue_type: issue.issue_type || "unknown",
            });
            await this._fetchValidation();
            this._showToast("Issue suppressed");
        }
        catch (err) {
            console.error("Failed to suppress issue:", err);
        }
        finally {
            this._suppressionInProgress = false;
        }
    }
    async _onSuppressionsChanged(action) {
        await this._fetchValidation();
        // If no more suppressions, go back to issues view
        if ((this._validationData?.suppressed_count || 0) === 0) {
            this._view = "issues";
        }
        if (action === "restore") {
            this._showToast("Issue restored");
        }
        else if (action === "clear-all") {
            this._showToast("All suppressions cleared");
        }
        else {
            this._showToast("Suppressions updated");
        }
    }
    _showToast(message) {
        this._toastMessage = message;
        this._toastVisible = true;
        if (this._toastTimeout) {
            clearTimeout(this._toastTimeout);
        }
        this._toastTimeout = setTimeout(() => {
            this._toastVisible = false;
        }, 3000);
    }
    async _applyFix(issue, fix) {
        const suggestedValue = fix.suggested_value || fix.fix_value;
        if (!suggestedValue) {
            this._showToast("No replacement value available");
            return;
        }
        try {
            const preview = await this.hass.callWS({
                type: "autodoctor/fix_preview",
                automation_id: issue.automation_id,
                location: issue.location,
                current_value: fix.current_value ?? null,
                suggested_value: suggestedValue,
            });
            if (!preview.applicable) {
                this._showToast(preview.reason || "Fix no longer applies");
                return;
            }
            const fromValue = preview.current_value || fix.current_value || "(current)";
            const confirmMessage = `Apply fix?\n\n` +
                `${fromValue} -> ${suggestedValue}\n` +
                `Automation: ${issue.automation_name}`;
            if (!window.confirm(confirmMessage)) {
                return;
            }
            const result = await this.hass.callWS({
                type: "autodoctor/fix_apply",
                automation_id: issue.automation_id,
                location: issue.location,
                current_value: preview.current_value ?? null,
                suggested_value: suggestedValue,
            });
            if (!result.applied) {
                this._showToast("Fix was not applied");
                return;
            }
            this._canUndoLastFix = true;
            await this._fetchValidation(false);
            this._showToast("Fix applied");
        }
        catch (err) {
            console.error("Failed to apply fix:", err);
            this._showToast("Failed to apply fix");
        }
    }
    async _undoLastFix() {
        try {
            const result = await this.hass.callWS({
                type: "autodoctor/fix_undo",
            });
            if (!result.undone) {
                this._showToast("Undo was not applied");
                return;
            }
            this._canUndoLastFix = false;
            await this._fetchValidation(false);
            this._showToast("Fix undone");
        }
        catch (err) {
            console.error("Failed to undo fix:", err);
            this._showToast("Unable to undo last fix");
            this._canUndoLastFix = false;
        }
    }
    static get styles() {
        return [autodocTokens, badgeStyles, cardLayoutStyles];
    }
    getCardSize() {
        return 3;
    }
    getGridOptions() {
        return {
            columns: 12,
            min_columns: 4,
            rows: "auto",
        };
    }
};
AutodoctorCard.CLICK_COOLDOWN_MS = 2000; // 2 second minimum between clicks
AutodoctorCard.AUTO_REFRESH_MS = 10000; // 10 second background refresh
__decorate([
    n({ attribute: false })
], AutodoctorCard.prototype, "hass", void 0);
__decorate([
    n({ attribute: false })
], AutodoctorCard.prototype, "config", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_loading", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_error", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_validationData", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_runningValidation", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_dismissedSuggestions", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_view", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_toastMessage", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_toastVisible", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_cooldownUntil", void 0);
__decorate([
    r()
], AutodoctorCard.prototype, "_canUndoLastFix", void 0);
AutodoctorCard = AutodoctorCard_1 = __decorate([
    t("autodoctor-card")
], AutodoctorCard);
// Register card with HA
window.customCards = window.customCards || [];
window.customCards.push({
    type: "autodoctor-card",
    name: "Autodoctor Card",
    description: "Shows automation health and validation issues",
    preview: false,
    documentationURL: "https://github.com/mossipcams/autodoctor",
});

let AutodoctorCardEditor = class AutodoctorCardEditor extends i {
    setConfig(config) {
        this._config = config;
    }
    _valueChanged(ev) {
        if (!this._config || !this.hass) {
            return;
        }
        const target = ev.target;
        const newConfig = {
            ...this._config,
            [target.id]: target.value || undefined,
        };
        // Remove undefined values
        Object.keys(newConfig).forEach((key) => {
            if (newConfig[key] === undefined) {
                delete newConfig[key];
            }
        });
        const event = new CustomEvent("config-changed", {
            detail: { config: newConfig },
            bubbles: true,
            composed: true,
        });
        this.dispatchEvent(event);
    }
    render() {
        if (!this.hass || !this._config) {
            return b ``;
        }
        return b `
      <div class="card-config">
        <ha-textfield
          id="title"
          label="Title (optional)"
          .value=${this._config.title || ""}
          @change=${this._valueChanged}
          placeholder="Automation Health"
        ></ha-textfield>
      </div>
    `;
    }
    static get styles() {
        return i$3 `
      .card-config {
        padding: 16px;
      }
      ha-textfield {
        display: block;
      }
    `;
    }
};
__decorate([
    n({ attribute: false })
], AutodoctorCardEditor.prototype, "hass", void 0);
__decorate([
    r()
], AutodoctorCardEditor.prototype, "_config", void 0);
AutodoctorCardEditor = __decorate([
    t("autodoctor-card-editor")
], AutodoctorCardEditor);

var autodoctorCardEditor = /*#__PURE__*/Object.freeze({
    __proto__: null,
    get AutodoctorCardEditor () { return AutodoctorCardEditor; }
});

export { AutodoctorCard };
