function t(t,e,s,i){var o,r=arguments.length,a=r<3?e:null===i?i=Object.getOwnPropertyDescriptor(e,s):i;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)a=Reflect.decorate(t,e,s,i);else for(var n=t.length-1;n>=0;n--)(o=t[n])&&(a=(r<3?o(a):r>3?o(e,s,a):o(e,s))||a);return r>3&&a&&Object.defineProperty(e,s,a),a}"function"==typeof SuppressedError&&SuppressedError;
/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const e=globalThis,s=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,i=Symbol(),o=new WeakMap;let r=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==i)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(s&&void 0===t){const s=void 0!==e&&1===e.length;s&&(t=o.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&o.set(e,t))}return t}toString(){return this.cssText}};const a=(t,...e)=>{const s=1===t.length?t[0]:e.reduce((e,s,i)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+t[i+1],t[0]);return new r(s,t,i)},n=s?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const s of t.cssRules)e+=s.cssText;return(t=>new r("string"==typeof t?t:t+"",void 0,i))(e)})(t):t,{is:d,defineProperty:c,getOwnPropertyDescriptor:l,getOwnPropertyNames:p,getOwnPropertySymbols:u,getPrototypeOf:h}=Object,g=globalThis,m=g.trustedTypes,v=m?m.emptyScript:"",f=g.reactiveElementPolyfillSupport,_=(t,e)=>t,y={toAttribute(t,e){switch(e){case Boolean:t=t?v:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let s=t;switch(e){case Boolean:s=null!==t;break;case Number:s=null===t?null:Number(t);break;case Object:case Array:try{s=JSON.parse(t)}catch(t){s=null}}return s}},b=(t,e)=>!d(t,e),$={attribute:!0,type:String,converter:y,reflect:!1,useDefault:!1,hasChanged:b};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */Symbol.metadata??=Symbol("metadata"),g.litPropertyMetadata??=new WeakMap;let x=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=$){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const s=Symbol(),i=this.getPropertyDescriptor(t,s,e);void 0!==i&&c(this.prototype,t,i)}}static getPropertyDescriptor(t,e,s){const{get:i,set:o}=l(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:i,set(e){const r=i?.call(this);o?.call(this,e),this.requestUpdate(t,r,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??$}static _$Ei(){if(this.hasOwnProperty(_("elementProperties")))return;const t=h(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(_("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(_("properties"))){const t=this.properties,e=[...p(t),...u(t)];for(const s of e)this.createProperty(s,t[s])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,s]of e)this.elementProperties.set(t,s)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const s=this._$Eu(t,e);void 0!==s&&this._$Eh.set(s,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const s=new Set(t.flat(1/0).reverse());for(const t of s)e.unshift(n(t))}else void 0!==t&&e.push(n(t));return e}static _$Eu(t,e){const s=e.attribute;return!1===s?void 0:"string"==typeof s?s:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,i)=>{if(s)t.adoptedStyleSheets=i.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const s of i){const i=document.createElement("style"),o=e.litNonce;void 0!==o&&i.setAttribute("nonce",o),i.textContent=s.cssText,t.appendChild(i)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){const s=this.constructor.elementProperties.get(t),i=this.constructor._$Eu(t,s);if(void 0!==i&&!0===s.reflect){const o=(void 0!==s.converter?.toAttribute?s.converter:y).toAttribute(e,s.type);this._$Em=t,null==o?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(t,e){const s=this.constructor,i=s._$Eh.get(t);if(void 0!==i&&this._$Em!==i){const t=s.getPropertyOptions(i),o="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:y;this._$Em=i;const r=o.fromAttribute(e,t.type);this[i]=r??this._$Ej?.get(i)??r,this._$Em=null}}requestUpdate(t,e,s,i=!1,o){if(void 0!==t){const r=this.constructor;if(!1===i&&(o=this[t]),s??=r.getPropertyOptions(t),!((s.hasChanged??b)(o,e)||s.useDefault&&s.reflect&&o===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,s))))return;this.C(t,e,s)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:i,wrapped:o},r){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),!0!==o||void 0!==r)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),!0===i&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,s]of t){const{wrapped:t}=s,i=this[e];!0!==t||this._$AL.has(e)||void 0===i||this.C(e,void 0,s,i)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};x.elementStyles=[],x.shadowRootOptions={mode:"open"},x[_("elementProperties")]=new Map,x[_("finalized")]=new Map,f?.({ReactiveElement:x}),(g.reactiveElementVersions??=[]).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const w=globalThis,A=t=>t,S=w.trustedTypes,k=S?S.createPolicy("lit-html",{createHTML:t=>t}):void 0,E="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,z="?"+C,P=`<${z}>`,R=document,O=()=>R.createComment(""),U=t=>null===t||"object"!=typeof t&&"function"!=typeof t,M=Array.isArray,I="[ \t\n\f\r]",T=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,H=/-->/g,D=/>/g,N=RegExp(`>|${I}(?:([^\\s"'>=/]+)(${I}*=${I}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),j=/'/g,L=/"/g,V=/^(?:script|style|textarea|title)$/i,q=(t=>(e,...s)=>({_$litType$:t,strings:e,values:s}))(1),B=Symbol.for("lit-noChange"),W=Symbol.for("lit-nothing"),F=new WeakMap,K=R.createTreeWalker(R,129);function J(t,e){if(!M(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==k?k.createHTML(e):e}const G=(t,e)=>{const s=t.length-1,i=[];let o,r=2===e?"<svg>":3===e?"<math>":"",a=T;for(let e=0;e<s;e++){const s=t[e];let n,d,c=-1,l=0;for(;l<s.length&&(a.lastIndex=l,d=a.exec(s),null!==d);)l=a.lastIndex,a===T?"!--"===d[1]?a=H:void 0!==d[1]?a=D:void 0!==d[2]?(V.test(d[2])&&(o=RegExp("</"+d[2],"g")),a=N):void 0!==d[3]&&(a=N):a===N?">"===d[0]?(a=o??T,c=-1):void 0===d[1]?c=-2:(c=a.lastIndex-d[2].length,n=d[1],a=void 0===d[3]?N:'"'===d[3]?L:j):a===L||a===j?a=N:a===H||a===D?a=T:(a=N,o=void 0);const p=a===N&&t[e+1].startsWith("/>")?" ":"";r+=a===T?s+P:c>=0?(i.push(n),s.slice(0,c)+E+s.slice(c)+C+p):s+C+(-2===c?e:p)}return[J(t,r+(t[s]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),i]};class Z{constructor({strings:t,_$litType$:e},s){let i;this.parts=[];let o=0,r=0;const a=t.length-1,n=this.parts,[d,c]=G(t,e);if(this.el=Z.createElement(d,s),K.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(i=K.nextNode())&&n.length<a;){if(1===i.nodeType){if(i.hasAttributes())for(const t of i.getAttributeNames())if(t.endsWith(E)){const e=c[r++],s=i.getAttribute(t).split(C),a=/([.?@])?(.*)/.exec(e);n.push({type:1,index:o,name:a[2],strings:s,ctor:"."===a[1]?et:"?"===a[1]?st:"@"===a[1]?it:tt}),i.removeAttribute(t)}else t.startsWith(C)&&(n.push({type:6,index:o}),i.removeAttribute(t));if(V.test(i.tagName)){const t=i.textContent.split(C),e=t.length-1;if(e>0){i.textContent=S?S.emptyScript:"";for(let s=0;s<e;s++)i.append(t[s],O()),K.nextNode(),n.push({type:2,index:++o});i.append(t[e],O())}}}else if(8===i.nodeType)if(i.data===z)n.push({type:2,index:o});else{let t=-1;for(;-1!==(t=i.data.indexOf(C,t+1));)n.push({type:7,index:o}),t+=C.length-1}o++}}static createElement(t,e){const s=R.createElement("template");return s.innerHTML=t,s}}function X(t,e,s=t,i){if(e===B)return e;let o=void 0!==i?s._$Co?.[i]:s._$Cl;const r=U(e)?void 0:e._$litDirective$;return o?.constructor!==r&&(o?._$AO?.(!1),void 0===r?o=void 0:(o=new r(t),o._$AT(t,s,i)),void 0!==i?(s._$Co??=[])[i]=o:s._$Cl=o),void 0!==o&&(e=X(t,o._$AS(t,e.values),o,i)),e}class Y{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:s}=this._$AD,i=(t?.creationScope??R).importNode(e,!0);K.currentNode=i;let o=K.nextNode(),r=0,a=0,n=s[0];for(;void 0!==n;){if(r===n.index){let e;2===n.type?e=new Q(o,o.nextSibling,this,t):1===n.type?e=new n.ctor(o,n.name,n.strings,this,t):6===n.type&&(e=new ot(o,this,t)),this._$AV.push(e),n=s[++a]}r!==n?.index&&(o=K.nextNode(),r++)}return K.currentNode=R,i}p(t){let e=0;for(const s of this._$AV)void 0!==s&&(void 0!==s.strings?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}}class Q{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,i){this.type=2,this._$AH=W,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=X(this,t,e),U(t)?t===W||null==t||""===t?(this._$AH!==W&&this._$AR(),this._$AH=W):t!==this._$AH&&t!==B&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>M(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==W&&U(this._$AH)?this._$AA.nextSibling.data=t:this.T(R.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:s}=t,i="number"==typeof s?this._$AC(t):(void 0===s.el&&(s.el=Z.createElement(J(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===i)this._$AH.p(e);else{const t=new Y(i,this),s=t.u(this.options);t.p(e),this.T(s),this._$AH=t}}_$AC(t){let e=F.get(t.strings);return void 0===e&&F.set(t.strings,e=new Z(t)),e}k(t){M(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let s,i=0;for(const o of t)i===e.length?e.push(s=new Q(this.O(O()),this.O(O()),this,this.options)):s=e[i],s._$AI(o),i++;i<e.length&&(this._$AR(s&&s._$AB.nextSibling,i),e.length=i)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=A(t).nextSibling;A(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class tt{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,i,o){this.type=1,this._$AH=W,this._$AN=void 0,this.element=t,this.name=e,this._$AM=i,this.options=o,s.length>2||""!==s[0]||""!==s[1]?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=W}_$AI(t,e=this,s,i){const o=this.strings;let r=!1;if(void 0===o)t=X(this,t,e,0),r=!U(t)||t!==this._$AH&&t!==B,r&&(this._$AH=t);else{const i=t;let a,n;for(t=o[0],a=0;a<o.length-1;a++)n=X(this,i[s+a],e,a),n===B&&(n=this._$AH[a]),r||=!U(n)||n!==this._$AH[a],n===W?t=W:t!==W&&(t+=(n??"")+o[a+1]),this._$AH[a]=n}r&&!i&&this.j(t)}j(t){t===W?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class et extends tt{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===W?void 0:t}}class st extends tt{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==W)}}class it extends tt{constructor(t,e,s,i,o){super(t,e,s,i,o),this.type=5}_$AI(t,e=this){if((t=X(this,t,e,0)??W)===B)return;const s=this._$AH,i=t===W&&s!==W||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,o=t!==W&&(s===W||i);i&&this.element.removeEventListener(this.name,this,s),o&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class ot{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){X(this,t)}}const rt=w.litHtmlPolyfillSupport;rt?.(Z,Q),(w.litHtmlVersions??=[]).push("3.3.2");const at=globalThis;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class nt extends x{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,s)=>{const i=s?.renderBefore??e;let o=i._$litPart$;if(void 0===o){const t=s?.renderBefore??null;i._$litPart$=o=new Q(e.insertBefore(O(),t),t,void 0,s??{})}return o._$AI(t),o})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return B}}nt._$litElement$=!0,nt.finalized=!0,at.litElementHydrateSupport?.({LitElement:nt});const dt=at.litElementPolyfillSupport;dt?.({LitElement:nt}),(at.litElementVersions??=[]).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const ct=t=>(e,s)=>{void 0!==s?s.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)},lt={attribute:!0,type:String,converter:y,reflect:!1,hasChanged:b},pt=(t=lt,e,s)=>{const{kind:i,metadata:o}=s;let r=globalThis.litPropertyMetadata.get(o);if(void 0===r&&globalThis.litPropertyMetadata.set(o,r=new Map),"setter"===i&&((t=Object.create(t)).wrapped=!0),r.set(s.name,t),"accessor"===i){const{name:i}=s;return{set(s){const o=e.get.call(this);e.set.call(this,s),this.requestUpdate(i,o,t,!0,s)},init(e){return void 0!==e&&this.C(i,void 0,t,e),e}}}if("setter"===i){const{name:i}=s;return function(s){const o=this[i];e.call(this,s),this.requestUpdate(i,o,t,!0,s)}}throw Error("Unsupported decorator location: "+i)};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function ut(t){return(e,s)=>"object"==typeof s?pt(t,e,s):((t,e,s)=>{const i=e.hasOwnProperty(s);return e.constructor.createProperty(s,t),i?Object.getOwnPropertyDescriptor(e,s):void 0})(t,e,s)}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function ht(t){return ut({...t,state:!0,attribute:!1})}function gt(t){return`${t.automation_id}:${t.entity_id}:${t.message}`}const mt=a`
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
`,vt=a`
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
      padding: 5px 10px;
      font-size: var(--autodoc-issue-size);
    }

    .badges-row {
      flex-wrap: wrap;
    }
  }

`,ft=a`
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
    opacity: 0.4;
    transition:
      opacity var(--autodoc-transition-fast),
      background var(--autodoc-transition-fast);
  }

  .issue:hover .suppress-btn {
    opacity: 0.6;
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
`,_t=a`
  ha-card {
    overflow: hidden;
    width: 100%;
    box-sizing: border-box;
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
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-md);
    }

    .run-btn {
      padding: var(--autodoc-spacing-sm) var(--autodoc-spacing-lg);
      font-size: var(--autodoc-name-size);
      min-height: 40px;
    }
  }

`,yt=a`
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
`;let bt=class extends nt{constructor(){super(...arguments),this.dismissedKeys=new Set}render(){const t=this.group;return q`
      <div class="automation-group ${t.has_error?"has-error":"has-warning"}">
        <div class="automation-header">
          <span class="automation-severity-icon" aria-hidden="true"
            >${t.has_error?"✕":"!"}</span
          >
          <span class="automation-name">${t.automation_name}</span>
          <span class="automation-badge">${t.issues.length}</span>
        </div>
        <div class="automation-issues">
          ${t.issues.map(t=>this._renderIssue(t))}
        </div>
        <a href="${t.edit_url}" class="edit-link" aria-label="Edit ${t.automation_name}">
          <span class="edit-text">Edit automation</span>
          <span class="edit-arrow" aria-hidden="true">\u2192</span>
        </a>
      </div>
    `}_renderIssue(t){const{issue:e,fix:s}=t,i="error"===e.severity,o=this.dismissedKeys.has(gt(e));return q`
      <div class="issue ${i?"error":"warning"}">
        <div class="issue-header">
          <span class="issue-icon" aria-hidden="true">${i?"✕":"!"}</span>
          <span class="issue-message">${e.message}</span>
          <button
            class="suppress-btn"
            @click=${()=>this._dispatchSuppress(e)}
            aria-label="Suppress this issue"
            title="Don't show this issue again"
          >
            \u2298
          </button>
        </div>
        ${s&&!o?q`
              <div class="fix-suggestion">
                <ha-icon class="fix-icon" icon="mdi:lightbulb-on-outline" style="--mdc-icon-size: 16px; color: var(--primary-color);" aria-hidden="true"></ha-icon>
                <div class="fix-content">
                  <span class="fix-description">${s.description}</span>
                  ${this._renderConfidencePill(s.confidence)}
                </div>
                <button
                  class="dismiss-btn"
                  @click=${()=>this._dispatchDismiss(e)}
                  aria-label="Dismiss suggestion"
                >
                  \u2715
                </button>
              </div>
            `:W}
      </div>
    `}_renderConfidencePill(t){if(t<=.6)return W;const e=t>.9;return q`
      <span class="confidence-pill ${e?"high":"medium"}">
        ${e?"High":"Medium"} confidence
      </span>
    `}_dispatchSuppress(t){this.dispatchEvent(new CustomEvent("suppress-issue",{detail:{issue:t},bubbles:!0,composed:!0}))}_dispatchDismiss(t){this.dispatchEvent(new CustomEvent("dismiss-suggestion",{detail:{issue:t},bubbles:!0,composed:!0}))}};bt.styles=[mt,ft],t([ut({attribute:!1})],bt.prototype,"group",void 0),t([ut({attribute:!1})],bt.prototype,"dismissedKeys",void 0),bt=t([ct("autodoc-issue-group")],bt);let $t=class extends nt{constructor(){super(...arguments),this.groups=[],this.running=!1,this._displayStates=[],this._showSummary=!1,this._staggerRunId=0}disconnectedCallback(){super.disconnectedCallback(),this._staggerRunId++}updated(t){if(super.updated(t),t.has("running")){const e=t.get("running");this.running?(this._displayStates=this.groups.map(()=>"neutral"),this._showSummary=!1):!0===e&&!this.running&&this.groups.length>0&&this._startStagger()}}async _startStagger(){const t=++this._staggerRunId;if(this._prefersReducedMotion())return this._displayStates=this.groups.map(t=>t.status),void(this._showSummary=!0);this._displayStates=this.groups.map(()=>"neutral"),this._showSummary=!1;for(let e=0;e<this.groups.length;e++){if(this._staggerRunId!==t)return;if(this._displayStates=[...this._displayStates],this._displayStates[e]="active",this.requestUpdate(),await this._delay(300),this._staggerRunId!==t)return;this._displayStates=[...this._displayStates],this._displayStates[e]=this.groups[e].status,e===this.groups.length-1&&(this._showSummary=!0),this.requestUpdate(),e<this.groups.length-1&&await this._delay(100)}}_delay(t){return new Promise(e=>setTimeout(e,t))}_prefersReducedMotion(){return window.matchMedia("(prefers-reduced-motion: reduce)").matches}render(){return q`
      <div class="pipeline" role="region" aria-label="Validation pipeline">
        ${this.groups.map((t,e)=>this._renderGroup(t,e))}
        ${this._showSummary?this._renderSummary():W}
      </div>
    `}_renderGroup(t,e){const s=this._displayStates[e]??t.status,i="neutral"!==s&&"active"!==s;return q`
      <div class="pipeline-group ${s}">
        <div class="group-header">
          <div class="group-status-icon" aria-hidden="true">
            ${"active"===s?q`<span class="active-dot"></span>`:i?this._statusIcon(s):W}
          </div>
          <span class="group-label">${t.label}</span>
          ${i?this._renderCounts(t):W}
        </div>
      </div>
    `}_statusIcon(t){return q`<span>${{pass:"✓",warning:"!",fail:"✕"}[t]||"?"}</span>`}_renderCounts(t){if(0===t.issue_count)return q`<span class="group-count pass-text">No issues</span>`;const e=[];return t.error_count>0&&e.push(`${t.error_count} error${1!==t.error_count?"s":""}`),t.warning_count>0&&e.push(`${t.warning_count} warning${1!==t.warning_count?"s":""}`),q`<span class="group-count ${t.status}-text">${e.join(", ")}</span>`}_getOverallStatus(){return this.groups.some(t=>"fail"===t.status)?"fail":this.groups.some(t=>"warning"===t.status)?"warning":"pass"}_renderSummary(){const t=this._getOverallStatus(),e=this.groups.reduce((t,e)=>t+e.error_count,0),s=this.groups.reduce((t,e)=>t+e.warning_count,0),i={pass:"All checks passed",warning:`${s} warning${1!==s?"s":""} found`,fail:`${e} error${1!==e?"s":""}${s>0?`, ${s} warning${1!==s?"s":""}`:""} found`};return q`
      <div
        class="pipeline-summary ${t}"
        role="status"
      >
        <span class="summary-icon" aria-hidden="true">${this._statusIcon(t)}</span>
        <span class="summary-text">${i[t]}</span>
      </div>
    `}};$t.styles=[mt,yt],t([ut({attribute:!1})],$t.prototype,"groups",void 0),t([ut({type:Boolean})],$t.prototype,"running",void 0),t([ht()],$t.prototype,"_displayStates",void 0),t([ht()],$t.prototype,"_showSummary",void 0),$t=t([ct("autodoc-pipeline")],$t);let xt=class extends nt{constructor(){super(...arguments),this._suppressions=[],this._loading=!0,this._error=null}connectedCallback(){super.connectedCallback(),this._fetchSuppressions()}async _fetchSuppressions(){this._loading=!0,this._error=null;try{const t=await this.hass.callWS({type:"autodoctor/list_suppressions"});this._suppressions=t.suppressions}catch(t){console.error("Failed to fetch suppressions:",t),this._error="Failed to load suppressions"}this._loading=!1}async _unsuppress(t){try{await this.hass.callWS({type:"autodoctor/unsuppress",key:t}),this._suppressions=this._suppressions.filter(e=>e.key!==t),this.dispatchEvent(new CustomEvent("suppressions-changed",{bubbles:!0,composed:!0}))}catch(t){console.error("Failed to unsuppress:",t)}}async _clearAll(){try{await this.hass.callWS({type:"autodoctor/clear_suppressions"}),this._suppressions=[],this.dispatchEvent(new CustomEvent("suppressions-changed",{bubbles:!0,composed:!0}))}catch(t){console.error("Failed to clear suppressions:",t)}}render(){return this._loading?q`<div class="loading">Loading suppressions...</div>`:this._error?q`<div class="error">${this._error}</div>`:0===this._suppressions.length?q`<div class="empty">No suppressed issues</div>`:q`
      <div class="suppressions-list">
        <div class="suppressions-header">
          <span class="suppressions-title"
            >${this._suppressions.length} suppressed
            issue${1!==this._suppressions.length?"s":""}</span
          >
          <button class="clear-all-btn" @click=${this._clearAll}>Clear all</button>
        </div>
        ${this._suppressions.map(t=>this._renderSuppression(t))}
      </div>
    `}_renderSuppression(t){return q`
      <div class="suppression-item">
        <div class="suppression-info">
          <span class="suppression-automation"
            >${t.automation_name||t.automation_id}</span
          >
          <span class="suppression-detail"
            >${t.entity_id}${t.message?` — ${t.message}`:""}</span
          >
        </div>
        <button
          class="restore-btn"
          @click=${()=>this._unsuppress(t.key)}
          title="Restore this issue"
          aria-label="Restore suppressed issue"
        >
          <ha-icon icon="mdi:eye-outline" style="--mdc-icon-size: 18px;"></ha-icon>
        </button>
      </div>
    `}static get styles(){return[mt,a`
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
      `]}};var wt;t([ut({attribute:!1})],xt.prototype,"hass",void 0),t([ht()],xt.prototype,"_suppressions",void 0),t([ht()],xt.prototype,"_loading",void 0),t([ht()],xt.prototype,"_error",void 0),xt=t([ct("autodoc-suppressions")],xt);console.info("%c AUTODOCTOR-CARD %c 2.11.0 ","color: white; background: #3498db; font-weight: bold;","color: #3498db; background: white; font-weight: bold;");let At=wt=class extends nt{constructor(){super(...arguments),this._loading=!0,this._error=null,this._validationData=null,this._runningValidation=!1,this._dismissedSuggestions=new Set,this._view="issues",this._validationRequestId=0,this._suppressionInProgress=!1,this._lastValidationClick=0}setConfig(t){this.config=t}static getStubConfig(){return{type:"custom:autodoctor-card"}}static async getConfigElement(){return await Promise.resolve().then(function(){return kt}),document.createElement("autodoctor-card-editor")}async firstUpdated(){await this._fetchValidation()}async _fetchValidation(){const t=++this._validationRequestId;this._loading=!0;try{this._error=null;const e=await this.hass.callWS({type:"autodoctor/validation/steps"});t===this._validationRequestId&&(this._validationData=e)}catch(e){t===this._validationRequestId&&(console.error("Failed to fetch validation data:",e),this._error="Failed to load validation data")}t===this._validationRequestId&&(this._loading=!1)}async _runValidation(){const t=Date.now();if(this._runningValidation||t-this._lastValidationClick<wt.CLICK_COOLDOWN_MS)return;this._lastValidationClick=t;const e=++this._validationRequestId;this._runningValidation=!0;try{const t=await this.hass.callWS({type:"autodoctor/validation/run_steps"});e===this._validationRequestId&&(this._validationData=t)}catch(t){e===this._validationRequestId&&console.error("Failed to run validation:",t)}e===this._validationRequestId&&(this._runningValidation=!1)}_groupIssuesByAutomation(t){const e=new Map;for(const s of t){const{issue:t,edit_url:i}=s,o=t.automation_id;e.has(o)||e.set(o,{automation_id:t.automation_id,automation_name:t.automation_name,issues:[],edit_url:i,has_error:!1,error_count:0,warning_count:0});const r=e.get(o);r.issues.push(s),"error"===t.severity?(r.has_error=!0,r.error_count++):r.warning_count++}return Array.from(e.values())}_getCounts(t){if(!t)return{errors:0,warnings:0,healthy:0,suppressed:0};let e=0,s=0;for(const i of t.issues)"error"===i.issue.severity?e++:s++;return{errors:e,warnings:s,healthy:t.healthy_count,suppressed:t.suppressed_count||0}}render(){const t=this.config.title||"Autodoctor";if(this._loading)return this._renderLoading(t);if(this._error)return this._renderError(t);const e=this._validationData;if(!e)return this._renderEmpty(t);const s=this._groupIssuesByAutomation(e.issues),i=this._getCounts(e),o=e.issues.length>0,r=!!e.last_run;return q`
      <ha-card>
        ${this._renderHeader(t)}
        <div class="card-content">
          ${this._renderBadges(i)}
          ${r?q`<autodoc-pipeline
                .groups=${e.groups||[]}
                ?running=${this._runningValidation}
              ></autodoc-pipeline>`:W}
          ${"suppressions"===this._view?q`<autodoc-suppressions
                .hass=${this.hass}
                @suppressions-changed=${()=>this._onSuppressionsChanged()}
              ></autodoc-suppressions>`:o?s.map(t=>q`
                    <autodoc-issue-group
                      .group=${t}
                      .dismissedKeys=${this._dismissedSuggestions}
                      @suppress-issue=${t=>this._suppressIssue(t.detail.issue)}
                      @dismiss-suggestion=${t=>this._dismissSuggestion(t.detail.issue)}
                    ></autodoc-issue-group>
                  `):r?this._renderAllHealthy(i.healthy):this._renderFirstRun()}
        </div>
        ${this._renderFooter()}
      </ha-card>
    `}_renderLoading(t){return q`
      <ha-card>
        <div class="header">
          <h2 class="title">${t}</h2>
        </div>
        <div class="card-content loading-state">
          <div class="spinner" aria-label="Loading"></div>
          <span class="loading-text">Checking automations...</span>
        </div>
      </ha-card>
    `}_renderError(t){return q`
      <ha-card>
        <div class="header">
          <h2 class="title">${t}</h2>
        </div>
        <div class="card-content error-state">
          <div class="error-icon" aria-hidden="true">\u26A0</div>
          <span class="error-text">${this._error}</span>
          <button class="retry-btn" @click=${()=>this._fetchValidation()}>Try again</button>
        </div>
      </ha-card>
    `}_renderEmpty(t){return q`
      <ha-card>
        ${this._renderHeader(t)}
        <div class="card-content empty-state">
          <span class="empty-text">No data available</span>
        </div>
      </ha-card>
    `}_renderHeader(t){return q`
      <div class="header">
        <h2 class="title">${t}</h2>
      </div>
    `}_renderAllHealthy(t){return q`
      <div class="all-healthy">
        <div class="healthy-icon" aria-hidden="true">\u2713</div>
        <div class="healthy-message">
          <span class="healthy-title">All systems healthy</span>
          <span class="healthy-subtitle"
            >${t} automation${1!==t?"s":""} checked</span
          >
        </div>
      </div>
    `}_renderFirstRun(){return q`
      <div class="empty-state">
        <span class="empty-text">Click "Run Validation" to scan your automations</span>
      </div>
    `}_renderBadges(t){return function(t,e,s){const i="suppressions"===s,o=i?()=>e?.("issues"):W,r=i?"cursor: pointer;":"";return q`
    <div class="badges-row">
      ${t.errors>0?q`<span
            class="badge badge-error"
            title="${t.errors} error${1!==t.errors?"s":""}"
            style=${r}
            @click=${o}
          >
            <span class="badge-icon" aria-hidden="true">\u2715</span>
            <span class="badge-count">${t.errors}</span>
          </span>`:W}
      ${t.warnings>0?q`<span
            class="badge badge-warning"
            title="${t.warnings} warning${1!==t.warnings?"s":""}"
            style=${r}
            @click=${o}
          >
            <span class="badge-icon" aria-hidden="true">!</span>
            <span class="badge-count">${t.warnings}</span>
          </span>`:W}
      ${t.healthy>0?q`<span
            class="badge badge-healthy"
            title="${t.healthy} healthy"
            style=${r}
            @click=${o}
          >
            <span class="badge-icon" aria-hidden="true">\u2713</span>
            <span class="badge-count">${t.healthy}</span>
          </span>`:W}
      ${t.suppressed>0?q`<span
            class="badge badge-suppressed ${i?"badge-active":""}"
            title="${t.suppressed} suppressed"
            role="button"
            tabindex="0"
            @click=${()=>e?.(i?"issues":"suppressions")}
            @keydown=${t=>{"Enter"!==t.key&&" "!==t.key||(t.preventDefault(),e?.(i?"issues":"suppressions"))}}
            style="cursor: pointer;"
          >
            <span class="badge-icon" aria-hidden="true">\u2298</span>
            <span class="badge-count">${t.suppressed}</span>
          </span>`:W}
    </div>
  `}(t,t=>{this._view=t},this._view)}_renderFooter(){const t=this._runningValidation||this._loading,e=t||Date.now()-this._lastValidationClick<wt.CLICK_COOLDOWN_MS;return q`
      <div class="footer">
        <button
          class="run-btn ${t?"running":""}"
          @click=${()=>this._runValidation()}
          ?disabled=${e}
        >
          <span class="run-icon" aria-hidden="true">${t?"↻":"▶"}</span>
          <span class="run-text">${t?"Running...":"Run Validation"}</span>
        </button>
        ${this._validationData?.last_run?q` <span class="last-run"
              >Last run: ${this._formatLastRun(this._validationData.last_run)}</span
            >`:W}
      </div>
    `}_formatLastRun(t){const e=new Date(t),s=(new Date).getTime()-e.getTime(),i=Math.floor(s/6e4);if(i<1)return"just now";if(i<60)return`${i}m ago`;const o=Math.floor(i/60);if(o<24)return`${o}h ago`;return`${Math.floor(o/24)}d ago`}_dismissSuggestion(t){const e=gt(t);this._dismissedSuggestions=new Set([...this._dismissedSuggestions,e])}async _suppressIssue(t){if(!this._suppressionInProgress){this._suppressionInProgress=!0;try{await this.hass.callWS({type:"autodoctor/suppress",automation_id:t.automation_id,entity_id:t.entity_id,issue_type:t.issue_type||"unknown"}),await this._fetchValidation()}catch(t){console.error("Failed to suppress issue:",t)}finally{this._suppressionInProgress=!1}}}async _onSuppressionsChanged(){await this._fetchValidation(),0===(this._validationData?.suppressed_count||0)&&(this._view="issues")}static get styles(){return[mt,vt,_t]}getCardSize(){return 3}getGridOptions(){return{columns:12,min_columns:4,rows:"auto"}}};At.CLICK_COOLDOWN_MS=2e3,t([ut({attribute:!1})],At.prototype,"hass",void 0),t([ut({attribute:!1})],At.prototype,"config",void 0),t([ht()],At.prototype,"_loading",void 0),t([ht()],At.prototype,"_error",void 0),t([ht()],At.prototype,"_validationData",void 0),t([ht()],At.prototype,"_runningValidation",void 0),t([ht()],At.prototype,"_dismissedSuggestions",void 0),t([ht()],At.prototype,"_view",void 0),At=wt=t([ct("autodoctor-card")],At),window.customCards=window.customCards||[],window.customCards.push({type:"autodoctor-card",name:"Autodoctor Card",description:"Shows automation health and validation issues",preview:!1,documentationURL:"https://github.com/mossipcams/autodoctor"});let St=class extends nt{setConfig(t){this._config=t}_valueChanged(t){if(!this._config||!this.hass)return;const e=t.target,s={...this._config,[e.id]:e.value||void 0};Object.keys(s).forEach(t=>{void 0===s[t]&&delete s[t]});const i=new CustomEvent("config-changed",{detail:{config:s},bubbles:!0,composed:!0});this.dispatchEvent(i)}render(){return this.hass&&this._config?q`
      <div class="card-config">
        <ha-textfield
          id="title"
          label="Title (optional)"
          .value=${this._config.title||""}
          @change=${this._valueChanged}
          placeholder="Automation Health"
        ></ha-textfield>
      </div>
    `:q``}static get styles(){return a`
      .card-config {
        padding: 16px;
      }
      ha-textfield {
        display: block;
      }
    `}};t([ut({attribute:!1})],St.prototype,"hass",void 0),t([ht()],St.prototype,"_config",void 0),St=t([ct("autodoctor-card-editor")],St);var kt=Object.freeze({__proto__:null,get AutodoctorCardEditor(){return St}});export{At as AutodoctorCard};
