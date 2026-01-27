function t(t,e,o,r){var i,s=arguments.length,a=s<3?e:null===r?r=Object.getOwnPropertyDescriptor(e,o):r;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)a=Reflect.decorate(t,e,o,r);else for(var n=t.length-1;n>=0;n--)(i=t[n])&&(a=(s<3?i(a):s>3?i(e,o,a):i(e,o))||a);return s>3&&a&&Object.defineProperty(e,o,a),a}"function"==typeof SuppressedError&&SuppressedError;
/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const e=globalThis,o=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,r=Symbol(),i=new WeakMap;let s=class{constructor(t,e,o){if(this._$cssResult$=!0,o!==r)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(o&&void 0===t){const o=void 0!==e&&1===e.length;o&&(t=i.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),o&&i.set(e,t))}return t}toString(){return this.cssText}};const a=(t,...e)=>{const o=1===t.length?t[0]:e.reduce((e,o,r)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+t[r+1],t[0]);return new s(o,t,r)},n=o?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const o of t.cssRules)e+=o.cssText;return(t=>new s("string"==typeof t?t:t+"",void 0,r))(e)})(t):t,{is:c,defineProperty:d,getOwnPropertyDescriptor:l,getOwnPropertyNames:h,getOwnPropertySymbols:u,getPrototypeOf:p}=Object,g=globalThis,f=g.trustedTypes,m=f?f.emptyScript:"",v=g.reactiveElementPolyfillSupport,_=(t,e)=>t,y={toAttribute(t,e){switch(e){case Boolean:t=t?m:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let o=t;switch(e){case Boolean:o=null!==t;break;case Number:o=null===t?null:Number(t);break;case Object:case Array:try{o=JSON.parse(t)}catch(t){o=null}}return o}},b=(t,e)=>!c(t,e),$={attribute:!0,type:String,converter:y,reflect:!1,useDefault:!1,hasChanged:b};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */Symbol.metadata??=Symbol("metadata"),g.litPropertyMetadata??=new WeakMap;let x=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=$){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const o=Symbol(),r=this.getPropertyDescriptor(t,o,e);void 0!==r&&d(this.prototype,t,r)}}static getPropertyDescriptor(t,e,o){const{get:r,set:i}=l(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:r,set(e){const s=r?.call(this);i?.call(this,e),this.requestUpdate(t,s,o)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??$}static _$Ei(){if(this.hasOwnProperty(_("elementProperties")))return;const t=p(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(_("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(_("properties"))){const t=this.properties,e=[...h(t),...u(t)];for(const o of e)this.createProperty(o,t[o])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,o]of e)this.elementProperties.set(t,o)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const o=this._$Eu(t,e);void 0!==o&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const o=new Set(t.flat(1/0).reverse());for(const t of o)e.unshift(n(t))}else void 0!==t&&e.push(n(t));return e}static _$Eu(t,e){const o=e.attribute;return!1===o?void 0:"string"==typeof o?o:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const o of e.keys())this.hasOwnProperty(o)&&(t.set(o,this[o]),delete this[o]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,r)=>{if(o)t.adoptedStyleSheets=r.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const o of r){const r=document.createElement("style"),i=e.litNonce;void 0!==i&&r.setAttribute("nonce",i),r.textContent=o.cssText,t.appendChild(r)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,o){this._$AK(t,o)}_$ET(t,e){const o=this.constructor.elementProperties.get(t),r=this.constructor._$Eu(t,o);if(void 0!==r&&!0===o.reflect){const i=(void 0!==o.converter?.toAttribute?o.converter:y).toAttribute(e,o.type);this._$Em=t,null==i?this.removeAttribute(r):this.setAttribute(r,i),this._$Em=null}}_$AK(t,e){const o=this.constructor,r=o._$Eh.get(t);if(void 0!==r&&this._$Em!==r){const t=o.getPropertyOptions(r),i="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:y;this._$Em=r;const s=i.fromAttribute(e,t.type);this[r]=s??this._$Ej?.get(r)??s,this._$Em=null}}requestUpdate(t,e,o,r=!1,i){if(void 0!==t){const s=this.constructor;if(!1===r&&(i=this[t]),o??=s.getPropertyOptions(t),!((o.hasChanged??b)(i,e)||o.useDefault&&o.reflect&&i===this._$Ej?.get(t)&&!this.hasAttribute(s._$Eu(t,o))))return;this.C(t,e,o)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:o,reflect:r,wrapped:i},s){o&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,s??e??this[t]),!0!==i||void 0!==s)||(this._$AL.has(t)||(this.hasUpdated||o||(e=void 0),this._$AL.set(t,e)),!0===r&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,o]of t){const{wrapped:t}=o,r=this[e];!0!==t||this._$AL.has(e)||void 0===r||this.C(e,void 0,o,r)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};x.elementStyles=[],x.shadowRootOptions={mode:"open"},x[_("elementProperties")]=new Map,x[_("finalized")]=new Map,v?.({ReactiveElement:x}),(g.reactiveElementVersions??=[]).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const A=globalThis,w=t=>t,E=A.trustedTypes,S=E?E.createPolicy("lit-html",{createHTML:t=>t}):void 0,C="$lit$",k=`lit$${Math.random().toFixed(9).slice(2)}$`,z="?"+k,T=`<${z}>`,P=document,O=()=>P.createComment(""),U=t=>null===t||"object"!=typeof t&&"function"!=typeof t,R=Array.isArray,H="[ \t\n\f\r]",M=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,D=/-->/g,N=/>/g,j=RegExp(`>|${H}(?:([^\\s"'>=/]+)(${H}*=${H}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),L=/'/g,V=/"/g,I=/^(?:script|style|textarea|title)$/i,B=(t=>(e,...o)=>({_$litType$:t,strings:e,values:o}))(1),W=Symbol.for("lit-noChange"),F=Symbol.for("lit-nothing"),q=new WeakMap,G=P.createTreeWalker(P,129);function J(t,e){if(!R(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==S?S.createHTML(e):e}const K=(t,e)=>{const o=t.length-1,r=[];let i,s=2===e?"<svg>":3===e?"<math>":"",a=M;for(let e=0;e<o;e++){const o=t[e];let n,c,d=-1,l=0;for(;l<o.length&&(a.lastIndex=l,c=a.exec(o),null!==c);)l=a.lastIndex,a===M?"!--"===c[1]?a=D:void 0!==c[1]?a=N:void 0!==c[2]?(I.test(c[2])&&(i=RegExp("</"+c[2],"g")),a=j):void 0!==c[3]&&(a=j):a===j?">"===c[0]?(a=i??M,d=-1):void 0===c[1]?d=-2:(d=a.lastIndex-c[2].length,n=c[1],a=void 0===c[3]?j:'"'===c[3]?V:L):a===V||a===L?a=j:a===D||a===N?a=M:(a=j,i=void 0);const h=a===j&&t[e+1].startsWith("/>")?" ":"";s+=a===M?o+T:d>=0?(r.push(n),o.slice(0,d)+C+o.slice(d)+k+h):o+k+(-2===d?e:h)}return[J(t,s+(t[o]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),r]};class Z{constructor({strings:t,_$litType$:e},o){let r;this.parts=[];let i=0,s=0;const a=t.length-1,n=this.parts,[c,d]=K(t,e);if(this.el=Z.createElement(c,o),G.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(r=G.nextNode())&&n.length<a;){if(1===r.nodeType){if(r.hasAttributes())for(const t of r.getAttributeNames())if(t.endsWith(C)){const e=d[s++],o=r.getAttribute(t).split(k),a=/([.?@])?(.*)/.exec(e);n.push({type:1,index:i,name:a[2],strings:o,ctor:"."===a[1]?et:"?"===a[1]?ot:"@"===a[1]?rt:tt}),r.removeAttribute(t)}else t.startsWith(k)&&(n.push({type:6,index:i}),r.removeAttribute(t));if(I.test(r.tagName)){const t=r.textContent.split(k),e=t.length-1;if(e>0){r.textContent=E?E.emptyScript:"";for(let o=0;o<e;o++)r.append(t[o],O()),G.nextNode(),n.push({type:2,index:++i});r.append(t[e],O())}}}else if(8===r.nodeType)if(r.data===z)n.push({type:2,index:i});else{let t=-1;for(;-1!==(t=r.data.indexOf(k,t+1));)n.push({type:7,index:i}),t+=k.length-1}i++}}static createElement(t,e){const o=P.createElement("template");return o.innerHTML=t,o}}function X(t,e,o=t,r){if(e===W)return e;let i=void 0!==r?o._$Co?.[r]:o._$Cl;const s=U(e)?void 0:e._$litDirective$;return i?.constructor!==s&&(i?._$AO?.(!1),void 0===s?i=void 0:(i=new s(t),i._$AT(t,o,r)),void 0!==r?(o._$Co??=[])[r]=i:o._$Cl=i),void 0!==i&&(e=X(t,i._$AS(t,e.values),i,r)),e}class Y{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:o}=this._$AD,r=(t?.creationScope??P).importNode(e,!0);G.currentNode=r;let i=G.nextNode(),s=0,a=0,n=o[0];for(;void 0!==n;){if(s===n.index){let e;2===n.type?e=new Q(i,i.nextSibling,this,t):1===n.type?e=new n.ctor(i,n.name,n.strings,this,t):6===n.type&&(e=new it(i,this,t)),this._$AV.push(e),n=o[++a]}s!==n?.index&&(i=G.nextNode(),s++)}return G.currentNode=P,r}p(t){let e=0;for(const o of this._$AV)void 0!==o&&(void 0!==o.strings?(o._$AI(t,o,e),e+=o.strings.length-2):o._$AI(t[e])),e++}}class Q{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,o,r){this.type=2,this._$AH=F,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=o,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=X(this,t,e),U(t)?t===F||null==t||""===t?(this._$AH!==F&&this._$AR(),this._$AH=F):t!==this._$AH&&t!==W&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>R(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==F&&U(this._$AH)?this._$AA.nextSibling.data=t:this.T(P.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:o}=t,r="number"==typeof o?this._$AC(t):(void 0===o.el&&(o.el=Z.createElement(J(o.h,o.h[0]),this.options)),o);if(this._$AH?._$AD===r)this._$AH.p(e);else{const t=new Y(r,this),o=t.u(this.options);t.p(e),this.T(o),this._$AH=t}}_$AC(t){let e=q.get(t.strings);return void 0===e&&q.set(t.strings,e=new Z(t)),e}k(t){R(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let o,r=0;for(const i of t)r===e.length?e.push(o=new Q(this.O(O()),this.O(O()),this,this.options)):o=e[r],o._$AI(i),r++;r<e.length&&(this._$AR(o&&o._$AB.nextSibling,r),e.length=r)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=w(t).nextSibling;w(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class tt{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,o,r,i){this.type=1,this._$AH=F,this._$AN=void 0,this.element=t,this.name=e,this._$AM=r,this.options=i,o.length>2||""!==o[0]||""!==o[1]?(this._$AH=Array(o.length-1).fill(new String),this.strings=o):this._$AH=F}_$AI(t,e=this,o,r){const i=this.strings;let s=!1;if(void 0===i)t=X(this,t,e,0),s=!U(t)||t!==this._$AH&&t!==W,s&&(this._$AH=t);else{const r=t;let a,n;for(t=i[0],a=0;a<i.length-1;a++)n=X(this,r[o+a],e,a),n===W&&(n=this._$AH[a]),s||=!U(n)||n!==this._$AH[a],n===F?t=F:t!==F&&(t+=(n??"")+i[a+1]),this._$AH[a]=n}s&&!r&&this.j(t)}j(t){t===F?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class et extends tt{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===F?void 0:t}}class ot extends tt{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==F)}}class rt extends tt{constructor(t,e,o,r,i){super(t,e,o,r,i),this.type=5}_$AI(t,e=this){if((t=X(this,t,e,0)??F)===W)return;const o=this._$AH,r=t===F&&o!==F||t.capture!==o.capture||t.once!==o.once||t.passive!==o.passive,i=t!==F&&(o===F||r);r&&this.element.removeEventListener(this.name,this,o),i&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class it{constructor(t,e,o){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=o}get _$AU(){return this._$AM._$AU}_$AI(t){X(this,t)}}const st=A.litHtmlPolyfillSupport;st?.(Z,Q),(A.litHtmlVersions??=[]).push("3.3.2");const at=globalThis;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class nt extends x{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,o)=>{const r=o?.renderBefore??e;let i=r._$litPart$;if(void 0===i){const t=o?.renderBefore??null;r._$litPart$=i=new Q(e.insertBefore(O(),t),t,void 0,o??{})}return i._$AI(t),i})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return W}}nt._$litElement$=!0,nt.finalized=!0,at.litElementHydrateSupport?.({LitElement:nt});const ct=at.litElementPolyfillSupport;ct?.({LitElement:nt}),(at.litElementVersions??=[]).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const dt=t=>(e,o)=>{void 0!==o?o.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)},lt={attribute:!0,type:String,converter:y,reflect:!1,hasChanged:b},ht=(t=lt,e,o)=>{const{kind:r,metadata:i}=o;let s=globalThis.litPropertyMetadata.get(i);if(void 0===s&&globalThis.litPropertyMetadata.set(i,s=new Map),"setter"===r&&((t=Object.create(t)).wrapped=!0),s.set(o.name,t),"accessor"===r){const{name:r}=o;return{set(o){const i=e.get.call(this);e.set.call(this,o),this.requestUpdate(r,i,t,!0,o)},init(e){return void 0!==e&&this.C(r,void 0,t,e),e}}}if("setter"===r){const{name:r}=o;return function(o){const i=this[r];e.call(this,o),this.requestUpdate(r,i,t,!0,o)}}throw Error("Unsupported decorator location: "+r)};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function ut(t){return(e,o)=>"object"==typeof o?ht(t,e,o):((t,e,o)=>{const r=e.hasOwnProperty(o);return e.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(e,o):void 0})(t,e,o)}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function pt(t){return ut({...t,state:!0,attribute:!1})}let gt=class extends nt{constructor(){super(...arguments),this._loading=!0,this._error=null,this._activeTab="validation",this._validationData=null,this._outcomesData=null,this._runningValidation=!1,this._runningOutcomes=!1,this._isRefreshing=!1}setConfig(t){this.config=t}static getStubConfig(){return{type:"custom:autodoctor-card"}}static async getConfigElement(){return await Promise.resolve().then(function(){return mt}),document.createElement("autodoctor-card-editor")}async firstUpdated(){await this._fetchValidation()}_switchTab(t){this._activeTab=t,"validation"!==t||this._validationData?"outcomes"!==t||this._outcomesData||this._fetchOutcomes():this._fetchValidation()}async _fetchValidation(){this._loading=!0;try{this._error=null,this._validationData=await this.hass.callWS({type:"autodoctor/validation"})}catch(t){console.error("Failed to fetch validation data:",t),this._error="Failed to load validation data"}this._loading=!1}async _fetchOutcomes(){this._loading=!0;try{this._error=null,this._outcomesData=await this.hass.callWS({type:"autodoctor/outcomes"})}catch(t){console.error("Failed to fetch outcomes data:",t),this._error="Failed to load outcomes data"}this._loading=!1}async _runValidation(){this._runningValidation=!0;try{this._validationData=await this.hass.callWS({type:"autodoctor/validation/run"})}catch(t){console.error("Failed to run validation:",t)}this._runningValidation=!1}async _runOutcomes(){this._runningOutcomes=!0;try{this._outcomesData=await this.hass.callWS({type:"autodoctor/outcomes/run"})}catch(t){console.error("Failed to run outcomes:",t)}this._runningOutcomes=!1}async _refreshCurrentTab(){this._isRefreshing=!0,"validation"===this._activeTab?await this._fetchValidation():await this._fetchOutcomes(),this._isRefreshing=!1}_groupIssuesByAutomation(t){const e=new Map;for(const o of t){const{issue:t,edit_url:r}=o,i=t.automation_id;e.has(i)||e.set(i,{automation_id:t.automation_id,automation_name:t.automation_name,issues:[],edit_url:r,has_error:!1,error_count:0,warning_count:0});const s=e.get(i);s.issues.push(o),"error"===t.severity?(s.has_error=!0,s.error_count++):s.warning_count++}return Array.from(e.values())}_getCounts(t){if(!t)return{errors:0,warnings:0,healthy:0};let e=0,o=0;for(const r of t.issues)"error"===r.issue.severity?e++:o++;return{errors:e,warnings:o,healthy:t.healthy_count}}render(){const t=this.config.title||"Autodoctor";if(this._loading)return this._renderLoading(t);if(this._error)return this._renderError(t);const e="validation"===this._activeTab?this._validationData:this._outcomesData;if(!e)return this._renderEmpty(t);const o=this._groupIssuesByAutomation(e.issues),r=this._getCounts(e),i=e.issues.length>0;return B`
      <ha-card>
        ${this._renderHeader(t)}
        ${this._renderTabs()}
        <div class="card-content">
          ${this._renderBadges(r)}
          ${i?o.map(t=>this._renderAutomationGroup(t)):this._renderAllHealthy(r.healthy)}
        </div>
        ${this._renderTabFooter()}
      </ha-card>
    `}_renderLoading(t){return B`
      <ha-card>
        <div class="header">
          <h2 class="title">${t}</h2>
        </div>
        <div class="card-content loading-state">
          <div class="spinner" aria-label="Loading"></div>
          <span class="loading-text">Checking automations...</span>
        </div>
      </ha-card>
    `}_renderError(t){return B`
      <ha-card>
        <div class="header">
          <h2 class="title">${t}</h2>
        </div>
        <div class="card-content error-state">
          <div class="error-icon" aria-hidden="true">⚠</div>
          <span class="error-text">${this._error}</span>
          <button class="retry-btn" @click=${this._refreshCurrentTab}>
            Try again
          </button>
        </div>
      </ha-card>
    `}_renderEmpty(t){return B`
      <ha-card>
        ${this._renderHeader(t)}
        ${this._renderTabs()}
        <div class="card-content empty-state">
          <span class="empty-text">No data available</span>
        </div>
      </ha-card>
    `}_renderHeader(t){return B`
      <div class="header">
        <h2 class="title">${t}</h2>
        <button
          class="refresh-btn ${this._isRefreshing?"refreshing":""}"
          @click=${this._refreshCurrentTab}
          ?disabled=${this._isRefreshing}
          aria-label="Refresh"
        >
          <span class="refresh-icon" aria-hidden="true">↻</span>
        </button>
      </div>
    `}_renderAllHealthy(t){return B`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">✓</div>
        <div class="healthy-message">
          <span class="healthy-title">All systems healthy</span>
          <span class="healthy-subtitle">${t} automation${1!==t?"s":""} checked</span>
        </div>
      </div>
    `}_renderTabs(){return B`
      <div class="tabs">
        <button
          class="tab ${"validation"===this._activeTab?"active":""}"
          @click=${()=>this._switchTab("validation")}
        >
          Validation
        </button>
        <button
          class="tab ${"outcomes"===this._activeTab?"active":""}"
          @click=${()=>this._switchTab("outcomes")}
        >
          Outcomes
        </button>
      </div>
    `}_renderBadges(t){return B`
      <div class="badges-row">
        ${t.errors>0?B`<span class="badge badge-error" title="${t.errors} error${1!==t.errors?"s":""}">
              <span class="badge-icon" aria-hidden="true">✕</span>
              <span class="badge-count">${t.errors}</span>
            </span>`:F}
        ${t.warnings>0?B`<span class="badge badge-warning" title="${t.warnings} warning${1!==t.warnings?"s":""}">
              <span class="badge-icon" aria-hidden="true">!</span>
              <span class="badge-count">${t.warnings}</span>
            </span>`:F}
        <span class="badge badge-healthy" title="${t.healthy} healthy">
          <span class="badge-icon" aria-hidden="true">✓</span>
          <span class="badge-count">${t.healthy}</span>
        </span>
      </div>
    `}_renderTabFooter(){const t="validation"===this._activeTab,e=t?this._runningValidation:this._runningOutcomes,o=t?this._validationData?.last_run:this._outcomesData?.last_run;return B`
      <div class="footer">
        <button
          class="run-btn ${e?"running":""}"
          @click=${()=>t?this._runValidation():this._runOutcomes()}
          ?disabled=${e}
        >
          <span class="run-icon" aria-hidden="true">${e?"↻":"▶"}</span>
          <span class="run-text">${e?"Running...":t?"Run Validation":"Run Outcomes"}</span>
        </button>
        ${o?B`
          <span class="last-run">Last run: ${this._formatLastRun(o)}</span>
        `:F}
      </div>
    `}_formatLastRun(t){const e=new Date(t),o=(new Date).getTime()-e.getTime(),r=Math.floor(o/6e4);if(r<1)return"just now";if(r<60)return`${r}m ago`;const i=Math.floor(r/60);if(i<24)return`${i}h ago`;return`${Math.floor(i/24)}d ago`}_renderAutomationGroup(t){return B`
      <div class="automation-group ${t.has_error?"has-error":"has-warning"}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true">${t.has_error?"✕":"!"}</span>
          <span class="automation-name">${t.automation_name}</span>
          <span class="automation-badge">${t.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${t.issues.map(t=>this._renderIssue(t))}
        </div>
        <a href="${t.edit_url}" class="edit-link" aria-label="Edit ${t.automation_name}">
          <span class="edit-text">Edit automation</span>
          <span class="edit-arrow" aria-hidden="true">→</span>
        </a>
      </div>
    `}_renderIssue(t){const{issue:e,fix:o}=t,r="error"===e.severity;return B`
      <div class="issue ${r?"error":"warning"}">
        <div class="issue-header">
          <span class="issue-icon" aria-hidden="true">${r?"✕":"!"}</span>
          <span class="issue-message">${e.message}</span>
        </div>
        ${o?B`
              <div class="fix-suggestion">
                <span class="fix-icon" aria-hidden="true">💡</span>
                <div class="fix-content">
                  <span class="fix-description">${o.description}</span>
                  ${this._renderConfidencePill(o.confidence)}
                </div>
              </div>
            `:F}
      </div>
    `}_renderConfidencePill(t){if(t<=.6)return F;const e=t>.9;return B`
      <span class="confidence-pill ${e?"high":"medium"}">
        ${e?"High":"Medium"} confidence
      </span>
    `}static get styles(){return a`
      :host {
        /* Typography */
        --autodoc-font-family: 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', sans-serif;
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

        font-family: var(--autodoc-font-family);
      }

      @media (prefers-reduced-motion: reduce) {
        :host {
          --autodoc-transition-fast: 0ms;
          --autodoc-transition-normal: 0ms;
        }
      }

      ha-card {
        overflow: hidden;
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

      /* Header refresh button */
      .header .refresh-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        padding: 0;
        background: transparent;
        color: var(--secondary-text-color);
        border: none;
        border-radius: 50%;
        cursor: pointer;
        transition: background var(--autodoc-transition-fast), color var(--autodoc-transition-fast);
      }

      .header .refresh-btn:hover:not(:disabled) {
        background: var(--divider-color, rgba(127, 127, 127, 0.2));
        color: var(--primary-color);
      }

      .header .refresh-btn:focus {
        outline: 2px solid var(--primary-color);
        outline-offset: 2px;
      }

      .header .refresh-btn:disabled {
        cursor: not-allowed;
        opacity: 0.6;
      }

      .header .refresh-btn .refresh-icon {
        font-size: 1.1rem;
      }

      .header .refresh-btn.refreshing .refresh-icon {
        animation: rotate 1s linear infinite;
      }

      /* Tabs */
      .tabs {
        display: flex;
        border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
      }

      .tab {
        flex: 1;
        padding: var(--autodoc-spacing-md) var(--autodoc-spacing-lg);
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        color: var(--secondary-text-color);
        font-family: var(--autodoc-font-family);
        font-size: var(--autodoc-issue-size);
        font-weight: 500;
        cursor: pointer;
        transition: color var(--autodoc-transition-fast), border-color var(--autodoc-transition-fast);
      }

      .tab:hover {
        color: var(--primary-text-color);
      }

      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      .tab:focus {
        outline: none;
        background: var(--divider-color, rgba(127, 127, 127, 0.1));
      }

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
        to { transform: rotate(360deg); }
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
        transition: background var(--autodoc-transition-fast), color var(--autodoc-transition-fast);
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
        font-size: var(--autodoc-issue-size);
        color: var(--secondary-text-color);
        line-height: 1.4;
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
        font-size: 0.875rem;
      }

      .fix-content {
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
        font-family: var(--autodoc-font-family);
        font-size: var(--autodoc-issue-size);
        font-weight: 500;
        cursor: pointer;
        transition: opacity var(--autodoc-transition-fast), transform var(--autodoc-transition-fast);
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

      .run-icon {
        font-size: 0.8rem;
      }

      .run-btn.running .run-icon {
        animation: rotate 1s linear infinite;
      }

      .run-text {
        font-family: var(--autodoc-font-family);
      }

      .last-run {
        color: var(--secondary-text-color);
        font-size: var(--autodoc-meta-size);
      }

      @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
    `}getCardSize(){return 3}};t([ut({attribute:!1})],gt.prototype,"hass",void 0),t([ut({attribute:!1})],gt.prototype,"config",void 0),t([pt()],gt.prototype,"_loading",void 0),t([pt()],gt.prototype,"_error",void 0),t([pt()],gt.prototype,"_activeTab",void 0),t([pt()],gt.prototype,"_validationData",void 0),t([pt()],gt.prototype,"_outcomesData",void 0),t([pt()],gt.prototype,"_runningValidation",void 0),t([pt()],gt.prototype,"_runningOutcomes",void 0),t([pt()],gt.prototype,"_isRefreshing",void 0),gt=t([dt("autodoctor-card")],gt),window.customCards=window.customCards||[],window.customCards.push({type:"autodoctor-card",name:"Autodoctor Card",description:"Shows automation health and validation issues",preview:!1,documentationURL:"https://github.com/mossipcams/autodoctor"});let ft=class extends nt{setConfig(t){this._config=t}_valueChanged(t){if(!this._config||!this.hass)return;const e=t.target,o={...this._config,[e.id]:e.value||void 0};Object.keys(o).forEach(t=>{void 0===o[t]&&delete o[t]});const r=new CustomEvent("config-changed",{detail:{config:o},bubbles:!0,composed:!0});this.dispatchEvent(r)}render(){return this.hass&&this._config?B`
      <div class="card-config">
        <div class="config-row">
          <label for="title">Title (optional)</label>
          <input
            id="title"
            type="text"
            .value=${this._config.title||""}
            @input=${this._valueChanged}
            placeholder="Automation Health"
          />
        </div>
      </div>
    `:B``}static get styles(){return a`
      .card-config {
        padding: 16px;
      }

      .config-row {
        display: flex;
        flex-direction: column;
        margin-bottom: 16px;
      }

      label {
        font-weight: 500;
        margin-bottom: 4px;
        color: var(--primary-text-color);
      }

      input {
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--card-background-color);
        color: var(--primary-text-color);
      }

      input:focus {
        outline: none;
        border-color: var(--primary-color);
      }
    `}};t([ut({attribute:!1})],ft.prototype,"hass",void 0),t([pt()],ft.prototype,"_config",void 0),ft=t([dt("autodoctor-card-editor")],ft);var mt=Object.freeze({__proto__:null,get AutodoctorCardEditor(){return ft}});export{gt as AutodoctorCard};
