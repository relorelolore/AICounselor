import{d as O,h as s,aj as oo,ak as to,al as ro,am as we,an as J,t as u,x as S,S as Be,u as ne,B as U,ao as Oe,D as ie,f as x,r as E,p as W,y as d,q as I,ap as Ee,i as D,H as L,J as re,aq as Q,ar as no,as as Y,at as ge,au as ve,R as io,av as ae,aw as lo,ax as ao,b as Se,ay as co,m as so,az as uo,af as vo,ad as mo,ab as ho,ae as fo,a6 as go,a2 as q,Y as H,V as ce,a1 as V,P as M,X as Re,O as Pe,a8 as Te,W as oe,ag as Ne,Q as Ae,aA as se,aB as po,ah as bo,ai as xo}from"./index-DzA_a9db.js";import{N as Co,V as yo}from"./Tooltip-WvQPc_rV.js";import{C as zo,N as Io,c as de}from"./Dropdown-DMysg0Xu.js";import{f as ue,u as me,_ as wo}from"./_plugin-vue_export-helper-BiLB3P_2.js";import{u as So}from"./use-compitable-B4W1URT9.js";const Ro=O({name:"ChevronDownFilled",render(){return s("svg",{viewBox:"0 0 16 16",fill:"none",xmlns:"http://www.w3.org/2000/svg"},s("path",{d:"M3.20041 5.73966C3.48226 5.43613 3.95681 5.41856 4.26034 5.70041L8 9.22652L11.7397 5.70041C12.0432 5.41856 12.5177 5.43613 12.7996 5.73966C13.0815 6.0432 13.0639 6.51775 12.7603 6.7996L8.51034 10.7996C8.22258 11.0668 7.77743 11.0668 7.48967 10.7996L3.23966 6.7996C2.93613 6.51775 2.91856 6.0432 3.20041 5.73966Z",fill:"currentColor"}))}});function Po(e){const{baseColor:t,textColor2:r,bodyColor:l,cardColor:a,dividerColor:i,actionColor:v,scrollbarColor:h,scrollbarColorHover:c,invertedColor:b}=e;return{textColor:r,textColorInverted:"#FFF",color:l,colorEmbedded:v,headerColor:a,headerColorInverted:b,footerColor:v,footerColorInverted:b,headerBorderColor:i,headerBorderColorInverted:b,footerBorderColor:i,footerBorderColorInverted:b,siderBorderColor:i,siderBorderColorInverted:b,siderColor:a,siderColorInverted:b,siderToggleButtonBorder:`1px solid ${i}`,siderToggleButtonColor:t,siderToggleButtonIconColor:r,siderToggleButtonIconColorInverted:r,siderToggleBarColor:we(l,h),siderToggleBarColorHover:we(l,c),__invertScrollbar:"true"}}const pe=oo({name:"Layout",common:ro,peers:{Scrollbar:to},self:Po}),$e=J("n-layout-sider"),be={type:String,default:"static"},To=u("layout",`
 color: var(--n-text-color);
 background-color: var(--n-color);
 box-sizing: border-box;
 position: relative;
 z-index: auto;
 flex: auto;
 overflow: hidden;
 transition:
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
`,[u("layout-scroll-container",`
 overflow-x: hidden;
 box-sizing: border-box;
 height: 100%;
 `),S("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),No={embedded:Boolean,position:be,nativeScrollbar:{type:Boolean,default:!0},scrollbarProps:Object,onScroll:Function,contentClass:String,contentStyle:{type:[String,Object],default:""},hasSider:Boolean,siderPlacement:{type:String,default:"left"}},Le=J("n-layout");function Fe(e){return O({name:e?"LayoutContent":"Layout",props:Object.assign(Object.assign({},U.props),No),setup(t){const r=E(null),l=E(null),{mergedClsPrefixRef:a,inlineThemeDisabled:i}=ne(t),v=U("Layout","-layout",To,pe,t,a);function h(g,R){if(t.nativeScrollbar){const{value:N}=r;N&&(R===void 0?N.scrollTo(g):N.scrollTo(g,R))}else{const{value:N}=l;N&&N.scrollTo(g,R)}}W(Le,t);let c=0,b=0;const _=g=>{var R;const N=g.target;c=N.scrollLeft,b=N.scrollTop,(R=t.onScroll)===null||R===void 0||R.call(t,g)};Oe(()=>{if(t.nativeScrollbar){const g=r.value;g&&(g.scrollTop=b,g.scrollLeft=c)}});const k={display:"flex",flexWrap:"nowrap",width:"100%",flexDirection:"row"},f={scrollTo:h},T=x(()=>{const{common:{cubicBezierEaseInOut:g},self:R}=v.value;return{"--n-bezier":g,"--n-color":t.embedded?R.colorEmbedded:R.color,"--n-text-color":R.textColor}}),w=i?ie("layout",x(()=>t.embedded?"e":""),T,t):void 0;return Object.assign({mergedClsPrefix:a,scrollableElRef:r,scrollbarInstRef:l,hasSiderStyle:k,mergedTheme:v,handleNativeElScroll:_,cssVars:i?void 0:T,themeClass:w?.themeClass,onRender:w?.onRender},f)},render(){var t;const{mergedClsPrefix:r,hasSider:l}=this;(t=this.onRender)===null||t===void 0||t.call(this);const a=l?this.hasSiderStyle:void 0,i=[this.themeClass,e&&`${r}-layout-content`,`${r}-layout`,`${r}-layout--${this.position}-positioned`];return s("div",{class:i,style:this.cssVars},this.nativeScrollbar?s("div",{ref:"scrollableElRef",class:[`${r}-layout-scroll-container`,this.contentClass],style:[this.contentStyle,a],onScroll:this.handleNativeElScroll},this.$slots):s(Be,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,contentClass:this.contentClass,contentStyle:[this.contentStyle,a]}),this.$slots))}})}const ke=Fe(!1),Ao=Fe(!0),ko=u("layout-header",`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 box-sizing: border-box;
 width: 100%;
 background-color: var(--n-color);
 color: var(--n-text-color);
`,[S("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 `),S("bordered",`
 border-bottom: solid 1px var(--n-border-color);
 `)]),_o={position:be,inverted:Boolean,bordered:{type:Boolean,default:!1}},Ho=O({name:"LayoutHeader",props:Object.assign(Object.assign({},U.props),_o),setup(e){const{mergedClsPrefixRef:t,inlineThemeDisabled:r}=ne(e),l=U("Layout","-layout-header",ko,pe,e,t),a=x(()=>{const{common:{cubicBezierEaseInOut:v},self:h}=l.value,c={"--n-bezier":v};return e.inverted?(c["--n-color"]=h.headerColorInverted,c["--n-text-color"]=h.textColorInverted,c["--n-border-color"]=h.headerBorderColorInverted):(c["--n-color"]=h.headerColor,c["--n-text-color"]=h.textColor,c["--n-border-color"]=h.headerBorderColor),c}),i=r?ie("layout-header",x(()=>e.inverted?"a":"b"),a,e):void 0;return{mergedClsPrefix:t,cssVars:r?void 0:a,themeClass:i?.themeClass,onRender:i?.onRender}},render(){var e;const{mergedClsPrefix:t}=this;return(e=this.onRender)===null||e===void 0||e.call(this),s("div",{class:[`${t}-layout-header`,this.themeClass,this.position&&`${t}-layout-header--${this.position}-positioned`,this.bordered&&`${t}-layout-header--bordered`],style:this.cssVars},this.$slots)}}),Bo=u("layout-sider",`
 flex-shrink: 0;
 box-sizing: border-box;
 position: relative;
 z-index: 1;
 color: var(--n-text-color);
 transition:
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 min-width .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 transform .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 background-color: var(--n-color);
 display: flex;
 justify-content: flex-end;
`,[S("bordered",[d("border",`
 content: "";
 position: absolute;
 top: 0;
 bottom: 0;
 width: 1px;
 background-color: var(--n-border-color);
 transition: background-color .3s var(--n-bezier);
 `)]),d("left-placement",[S("bordered",[d("border",`
 right: 0;
 `)])]),S("right-placement",`
 justify-content: flex-start;
 `,[S("bordered",[d("border",`
 left: 0;
 `)]),S("collapsed",[u("layout-toggle-button",[u("base-icon",`
 transform: rotate(180deg);
 `)]),u("layout-toggle-bar",[I("&:hover",[d("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])])]),u("layout-toggle-button",`
 left: 0;
 transform: translateX(-50%) translateY(-50%);
 `,[u("base-icon",`
 transform: rotate(0);
 `)]),u("layout-toggle-bar",`
 left: -28px;
 transform: rotate(180deg);
 `,[I("&:hover",[d("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})])])]),S("collapsed",[u("layout-toggle-bar",[I("&:hover",[d("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])]),u("layout-toggle-button",[u("base-icon",`
 transform: rotate(0);
 `)])]),u("layout-toggle-button",`
 transition:
 color .3s var(--n-bezier),
 right .3s var(--n-bezier),
 left .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 cursor: pointer;
 width: 24px;
 height: 24px;
 position: absolute;
 top: 50%;
 right: 0;
 border-radius: 50%;
 display: flex;
 align-items: center;
 justify-content: center;
 font-size: 18px;
 color: var(--n-toggle-button-icon-color);
 border: var(--n-toggle-button-border);
 background-color: var(--n-toggle-button-color);
 box-shadow: 0 2px 4px 0px rgba(0, 0, 0, .06);
 transform: translateX(50%) translateY(-50%);
 z-index: 1;
 `,[u("base-icon",`
 transition: transform .3s var(--n-bezier);
 transform: rotate(180deg);
 `)]),u("layout-toggle-bar",`
 cursor: pointer;
 height: 72px;
 width: 32px;
 position: absolute;
 top: calc(50% - 36px);
 right: -28px;
 `,[d("top, bottom",`
 position: absolute;
 width: 4px;
 border-radius: 2px;
 height: 38px;
 left: 14px;
 transition: 
 background-color .3s var(--n-bezier),
 transform .3s var(--n-bezier);
 `),d("bottom",`
 position: absolute;
 top: 34px;
 `),I("&:hover",[d("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})]),d("top, bottom",{backgroundColor:"var(--n-toggle-bar-color)"}),I("&:hover",[d("top, bottom",{backgroundColor:"var(--n-toggle-bar-color-hover)"})])]),d("border",`
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 width: 1px;
 transition: background-color .3s var(--n-bezier);
 `),u("layout-sider-scroll-container",`
 flex-grow: 1;
 flex-shrink: 0;
 box-sizing: border-box;
 height: 100%;
 opacity: 0;
 transition: opacity .3s var(--n-bezier);
 max-width: 100%;
 `),S("show-content",[u("layout-sider-scroll-container",{opacity:1})]),S("absolute-positioned",`
 position: absolute;
 left: 0;
 top: 0;
 bottom: 0;
 `)]),Oo=O({props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return s("div",{onClick:this.onClick,class:`${e}-layout-toggle-bar`},s("div",{class:`${e}-layout-toggle-bar__top`}),s("div",{class:`${e}-layout-toggle-bar__bottom`}))}}),Eo=O({name:"LayoutToggleButton",props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return s("div",{class:`${e}-layout-toggle-button`,onClick:this.onClick},s(Ee,{clsPrefix:e},{default:()=>s(zo,null)}))}}),$o={position:be,bordered:Boolean,collapsedWidth:{type:Number,default:48},width:{type:[Number,String],default:272},contentClass:String,contentStyle:{type:[String,Object],default:""},collapseMode:{type:String,default:"transform"},collapsed:{type:Boolean,default:void 0},defaultCollapsed:Boolean,showCollapsedContent:{type:Boolean,default:!0},showTrigger:{type:[Boolean,String],default:!1},nativeScrollbar:{type:Boolean,default:!0},inverted:Boolean,scrollbarProps:Object,triggerClass:String,triggerStyle:[String,Object],collapsedTriggerClass:String,collapsedTriggerStyle:[String,Object],"onUpdate:collapsed":[Function,Array],onUpdateCollapsed:[Function,Array],onAfterEnter:Function,onAfterLeave:Function,onExpand:[Function,Array],onCollapse:[Function,Array],onScroll:Function},Lo=O({name:"LayoutSider",props:Object.assign(Object.assign({},U.props),$o),setup(e){const t=D(Le),r=E(null),l=E(null),a=E(e.defaultCollapsed),i=me(re(e,"collapsed"),a),v=x(()=>ue(i.value?e.collapsedWidth:e.width)),h=x(()=>e.collapseMode!=="transform"?{}:{minWidth:ue(e.width)}),c=x(()=>t?t.siderPlacement:"left");function b(A,y){if(e.nativeScrollbar){const{value:z}=r;z&&(y===void 0?z.scrollTo(A):z.scrollTo(A,y))}else{const{value:z}=l;z&&z.scrollTo(A,y)}}function _(){const{"onUpdate:collapsed":A,onUpdateCollapsed:y,onExpand:z,onCollapse:K}=e,{value:F}=i;y&&L(y,!F),A&&L(A,!F),a.value=!F,F?z&&L(z):K&&L(K)}let k=0,f=0;const T=A=>{var y;const z=A.target;k=z.scrollLeft,f=z.scrollTop,(y=e.onScroll)===null||y===void 0||y.call(e,A)};Oe(()=>{if(e.nativeScrollbar){const A=r.value;A&&(A.scrollTop=f,A.scrollLeft=k)}}),W($e,{collapsedRef:i,collapseModeRef:re(e,"collapseMode")});const{mergedClsPrefixRef:w,inlineThemeDisabled:g}=ne(e),R=U("Layout","-layout-sider",Bo,pe,e,w);function N(A){var y,z;A.propertyName==="max-width"&&(i.value?(y=e.onAfterLeave)===null||y===void 0||y.call(e):(z=e.onAfterEnter)===null||z===void 0||z.call(e))}const X={scrollTo:b},j=x(()=>{const{common:{cubicBezierEaseInOut:A},self:y}=R.value,{siderToggleButtonColor:z,siderToggleButtonBorder:K,siderToggleBarColor:F,siderToggleBarColorHover:le}=y,B={"--n-bezier":A,"--n-toggle-button-color":z,"--n-toggle-button-border":K,"--n-toggle-bar-color":F,"--n-toggle-bar-color-hover":le};return e.inverted?(B["--n-color"]=y.siderColorInverted,B["--n-text-color"]=y.textColorInverted,B["--n-border-color"]=y.siderBorderColorInverted,B["--n-toggle-button-icon-color"]=y.siderToggleButtonIconColorInverted,B.__invertScrollbar=y.__invertScrollbar):(B["--n-color"]=y.siderColor,B["--n-text-color"]=y.textColor,B["--n-border-color"]=y.siderBorderColor,B["--n-toggle-button-icon-color"]=y.siderToggleButtonIconColor),B}),$=g?ie("layout-sider",x(()=>e.inverted?"a":"b"),j,e):void 0;return Object.assign({scrollableElRef:r,scrollbarInstRef:l,mergedClsPrefix:w,mergedTheme:R,styleMaxWidth:v,mergedCollapsed:i,scrollContainerStyle:h,siderPlacement:c,handleNativeElScroll:T,handleTransitionend:N,handleTriggerClick:_,inlineThemeDisabled:g,cssVars:j,themeClass:$?.themeClass,onRender:$?.onRender},X)},render(){var e;const{mergedClsPrefix:t,mergedCollapsed:r,showTrigger:l}=this;return(e=this.onRender)===null||e===void 0||e.call(this),s("aside",{class:[`${t}-layout-sider`,this.themeClass,`${t}-layout-sider--${this.position}-positioned`,`${t}-layout-sider--${this.siderPlacement}-placement`,this.bordered&&`${t}-layout-sider--bordered`,r&&`${t}-layout-sider--collapsed`,(!r||this.showCollapsedContent)&&`${t}-layout-sider--show-content`],onTransitionend:this.handleTransitionend,style:[this.inlineThemeDisabled?void 0:this.cssVars,{maxWidth:this.styleMaxWidth,width:ue(this.width)}]},this.nativeScrollbar?s("div",{class:[`${t}-layout-sider-scroll-container`,this.contentClass],onScroll:this.handleNativeElScroll,style:[this.scrollContainerStyle,{overflow:"auto"},this.contentStyle],ref:"scrollableElRef"},this.$slots):s(Be,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",style:this.scrollContainerStyle,contentStyle:this.contentStyle,contentClass:this.contentClass,theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,builtinThemeOverrides:this.inverted&&this.cssVars.__invertScrollbar==="true"?{colorHover:"rgba(255, 255, 255, .4)",color:"rgba(255, 255, 255, .3)"}:void 0}),this.$slots),l?l==="bar"?s(Oo,{clsPrefix:t,class:r?this.collapsedTriggerClass:this.triggerClass,style:r?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):s(Eo,{clsPrefix:t,class:r?this.collapsedTriggerClass:this.triggerClass,style:r?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):null,this.bordered?s("div",{class:`${t}-layout-sider__border`}):null)}}),Z=J("n-menu"),Me=J("n-submenu"),xe=J("n-menu-item-group"),_e=[I("&::before","background-color: var(--n-item-color-hover);"),d("arrow",`
 color: var(--n-arrow-color-hover);
 `),d("icon",`
 color: var(--n-item-icon-color-hover);
 `),u("menu-item-content-header",`
 color: var(--n-item-text-color-hover);
 `,[I("a",`
 color: var(--n-item-text-color-hover);
 `),d("extra",`
 color: var(--n-item-text-color-hover);
 `)])],He=[d("icon",`
 color: var(--n-item-icon-color-hover-horizontal);
 `),u("menu-item-content-header",`
 color: var(--n-item-text-color-hover-horizontal);
 `,[I("a",`
 color: var(--n-item-text-color-hover-horizontal);
 `),d("extra",`
 color: var(--n-item-text-color-hover-horizontal);
 `)])],Fo=I([u("menu",`
 background-color: var(--n-color);
 color: var(--n-item-text-color);
 overflow: hidden;
 transition: background-color .3s var(--n-bezier);
 box-sizing: border-box;
 font-size: var(--n-font-size);
 padding-bottom: 6px;
 `,[S("horizontal",`
 max-width: 100%;
 width: 100%;
 display: flex;
 overflow: hidden;
 padding-bottom: 0;
 `,[u("submenu","margin: 0;"),u("menu-item","margin: 0;"),u("menu-item-content",`
 padding: 0 20px;
 border-bottom: 2px solid #0000;
 `,[I("&::before","display: none;"),S("selected","border-bottom: 2px solid var(--n-border-color-horizontal)")]),u("menu-item-content",[S("selected",[d("icon","color: var(--n-item-icon-color-active-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-horizontal);
 `,[I("a","color: var(--n-item-text-color-active-horizontal);"),d("extra","color: var(--n-item-text-color-active-horizontal);")])]),S("child-active",`
 border-bottom: 2px solid var(--n-border-color-horizontal);
 `,[u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-horizontal);
 `,[I("a",`
 color: var(--n-item-text-color-child-active-horizontal);
 `),d("extra",`
 color: var(--n-item-text-color-child-active-horizontal);
 `)]),d("icon",`
 color: var(--n-item-icon-color-child-active-horizontal);
 `)]),Q("disabled",[Q("selected, child-active",[I("&:focus-within",He)]),S("selected",[G(null,[d("icon","color: var(--n-item-icon-color-active-hover-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover-horizontal);
 `,[I("a","color: var(--n-item-text-color-active-hover-horizontal);"),d("extra","color: var(--n-item-text-color-active-hover-horizontal);")])])]),S("child-active",[G(null,[d("icon","color: var(--n-item-icon-color-child-active-hover-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover-horizontal);
 `,[I("a","color: var(--n-item-text-color-child-active-hover-horizontal);"),d("extra","color: var(--n-item-text-color-child-active-hover-horizontal);")])])]),G("border-bottom: 2px solid var(--n-border-color-horizontal);",He)]),u("menu-item-content-header",[I("a","color: var(--n-item-text-color-horizontal);")])])]),Q("responsive",[u("menu-item-content-header",`
 overflow: hidden;
 text-overflow: ellipsis;
 `)]),S("collapsed",[u("menu-item-content",[S("selected",[I("&::before",`
 background-color: var(--n-item-color-active-collapsed) !important;
 `)]),u("menu-item-content-header","opacity: 0;"),d("arrow","opacity: 0;"),d("icon","color: var(--n-item-icon-color-collapsed);")])]),u("menu-item",`
 height: var(--n-item-height);
 margin-top: 6px;
 position: relative;
 `),u("menu-item-content",`
 box-sizing: border-box;
 line-height: 1.75;
 height: 100%;
 display: grid;
 grid-template-areas: "icon content arrow";
 grid-template-columns: auto 1fr auto;
 align-items: center;
 cursor: pointer;
 position: relative;
 padding-right: 18px;
 transition:
 background-color .3s var(--n-bezier),
 padding-left .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[I("> *","z-index: 1;"),I("&::before",`
 z-index: auto;
 content: "";
 background-color: #0000;
 position: absolute;
 left: 8px;
 right: 8px;
 top: 0;
 bottom: 0;
 pointer-events: none;
 border-radius: var(--n-border-radius);
 transition: background-color .3s var(--n-bezier);
 `),S("disabled",`
 opacity: .45;
 cursor: not-allowed;
 `),S("collapsed",[d("arrow","transform: rotate(0);")]),S("selected",[I("&::before","background-color: var(--n-item-color-active);"),d("arrow","color: var(--n-arrow-color-active);"),d("icon","color: var(--n-item-icon-color-active);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active);
 `,[I("a","color: var(--n-item-text-color-active);"),d("extra","color: var(--n-item-text-color-active);")])]),S("child-active",[u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active);
 `,[I("a",`
 color: var(--n-item-text-color-child-active);
 `),d("extra",`
 color: var(--n-item-text-color-child-active);
 `)]),d("arrow",`
 color: var(--n-arrow-color-child-active);
 `),d("icon",`
 color: var(--n-item-icon-color-child-active);
 `)]),Q("disabled",[Q("selected, child-active",[I("&:focus-within",_e)]),S("selected",[G(null,[d("arrow","color: var(--n-arrow-color-active-hover);"),d("icon","color: var(--n-item-icon-color-active-hover);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover);
 `,[I("a","color: var(--n-item-text-color-active-hover);"),d("extra","color: var(--n-item-text-color-active-hover);")])])]),S("child-active",[G(null,[d("arrow","color: var(--n-arrow-color-child-active-hover);"),d("icon","color: var(--n-item-icon-color-child-active-hover);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover);
 `,[I("a","color: var(--n-item-text-color-child-active-hover);"),d("extra","color: var(--n-item-text-color-child-active-hover);")])])]),S("selected",[G(null,[I("&::before","background-color: var(--n-item-color-active-hover);")])]),G(null,_e)]),d("icon",`
 grid-area: icon;
 color: var(--n-item-icon-color);
 transition:
 color .3s var(--n-bezier),
 font-size .3s var(--n-bezier),
 margin-right .3s var(--n-bezier);
 box-sizing: content-box;
 display: inline-flex;
 align-items: center;
 justify-content: center;
 `),d("arrow",`
 grid-area: arrow;
 font-size: 16px;
 color: var(--n-arrow-color);
 transform: rotate(180deg);
 opacity: 1;
 transition:
 color .3s var(--n-bezier),
 transform 0.2s var(--n-bezier),
 opacity 0.2s var(--n-bezier);
 `),u("menu-item-content-header",`
 grid-area: content;
 transition:
 color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 opacity: 1;
 white-space: nowrap;
 color: var(--n-item-text-color);
 `,[I("a",`
 outline: none;
 text-decoration: none;
 transition: color .3s var(--n-bezier);
 color: var(--n-item-text-color);
 `,[I("&::before",`
 content: "";
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),d("extra",`
 font-size: .93em;
 color: var(--n-group-text-color);
 transition: color .3s var(--n-bezier);
 `)])]),u("submenu",`
 cursor: pointer;
 position: relative;
 margin-top: 6px;
 `,[u("menu-item-content",`
 height: var(--n-item-height);
 `),u("submenu-children",`
 overflow: hidden;
 padding: 0;
 `,[no({duration:".2s"})])]),u("menu-item-group",[u("menu-item-group-title",`
 margin-top: 6px;
 color: var(--n-group-text-color);
 cursor: default;
 font-size: .93em;
 height: 36px;
 display: flex;
 align-items: center;
 transition:
 padding-left .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `)])]),u("menu-tooltip",[I("a",`
 color: inherit;
 text-decoration: none;
 `)]),u("menu-divider",`
 transition: background-color .3s var(--n-bezier);
 background-color: var(--n-divider-color);
 height: 1px;
 margin: 6px 18px;
 `)]);function G(e,t){return[S("hover",e,t),I("&:hover",e,t)]}const je=O({name:"MenuOptionContent",props:{collapsed:Boolean,disabled:Boolean,title:[String,Function],icon:Function,extra:[String,Function],showArrow:Boolean,childActive:Boolean,hover:Boolean,paddingLeft:Number,selected:Boolean,maxIconSize:{type:Number,required:!0},activeIconSize:{type:Number,required:!0},iconMarginRight:{type:Number,required:!0},clsPrefix:{type:String,required:!0},onClick:Function,tmNode:{type:Object,required:!0},isEllipsisPlaceholder:Boolean},setup(e){const{props:t}=D(Z);return{menuProps:t,style:x(()=>{const{paddingLeft:r}=e;return{paddingLeft:r&&`${r}px`}}),iconStyle:x(()=>{const{maxIconSize:r,activeIconSize:l,iconMarginRight:a}=e;return{width:`${r}px`,height:`${r}px`,fontSize:`${l}px`,marginRight:`${a}px`}})}},render(){const{clsPrefix:e,tmNode:t,menuProps:{renderIcon:r,renderLabel:l,renderExtra:a,expandIcon:i}}=this,v=r?r(t.rawNode):Y(this.icon);return s("div",{onClick:h=>{var c;(c=this.onClick)===null||c===void 0||c.call(this,h)},role:"none",class:[`${e}-menu-item-content`,{[`${e}-menu-item-content--selected`]:this.selected,[`${e}-menu-item-content--collapsed`]:this.collapsed,[`${e}-menu-item-content--child-active`]:this.childActive,[`${e}-menu-item-content--disabled`]:this.disabled,[`${e}-menu-item-content--hover`]:this.hover}],style:this.style},v&&s("div",{class:`${e}-menu-item-content__icon`,style:this.iconStyle,role:"none"},[v]),s("div",{class:`${e}-menu-item-content-header`,role:"none"},this.isEllipsisPlaceholder?this.title:l?l(t.rawNode):Y(this.title),this.extra||a?s("span",{class:`${e}-menu-item-content-header__extra`}," ",a?a(t.rawNode):Y(this.extra)):null),this.showArrow?s(Ee,{ariaHidden:!0,class:`${e}-menu-item-content__arrow`,clsPrefix:e},{default:()=>i?i(t.rawNode):s(Ro,null)}):null)}}),te=8;function Ce(e){const t=D(Z),{props:r,mergedCollapsedRef:l}=t,a=D(Me,null),i=D(xe,null),v=x(()=>r.mode==="horizontal"),h=x(()=>v.value?r.dropdownPlacement:"tmNodes"in e?"right-start":"right"),c=x(()=>{var f;return Math.max((f=r.collapsedIconSize)!==null&&f!==void 0?f:r.iconSize,r.iconSize)}),b=x(()=>{var f;return!v.value&&e.root&&l.value&&(f=r.collapsedIconSize)!==null&&f!==void 0?f:r.iconSize}),_=x(()=>{if(v.value)return;const{collapsedWidth:f,indent:T,rootIndent:w}=r,{root:g,isGroup:R}=e,N=w===void 0?T:w;return g?l.value?f/2-c.value/2:N:i&&typeof i.paddingLeftRef.value=="number"?T/2+i.paddingLeftRef.value:a&&typeof a.paddingLeftRef.value=="number"?(R?T/2:T)+a.paddingLeftRef.value:0}),k=x(()=>{const{collapsedWidth:f,indent:T,rootIndent:w}=r,{value:g}=c,{root:R}=e;return v.value||!R||!l.value?te:(w===void 0?T:w)+g+te-(f+g)/2});return{dropdownPlacement:h,activeIconSize:b,maxIconSize:c,paddingLeft:_,iconMarginRight:k,NMenu:t,NSubmenu:a,NMenuOptionGroup:i}}const ye={internalKey:{type:[String,Number],required:!0},root:Boolean,isGroup:Boolean,level:{type:Number,required:!0},title:[String,Function],extra:[String,Function]},Mo=O({name:"MenuDivider",setup(){const e=D(Z),{mergedClsPrefixRef:t,isHorizontalRef:r}=e;return()=>r.value?null:s("div",{class:`${t.value}-menu-divider`})}}),Ke=Object.assign(Object.assign({},ye),{tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function}),jo=ge(Ke),Ko=O({name:"MenuOption",props:Ke,setup(e){const t=Ce(e),{NSubmenu:r,NMenu:l,NMenuOptionGroup:a}=t,{props:i,mergedClsPrefixRef:v,mergedCollapsedRef:h}=l,c=r?r.mergedDisabledRef:a?a.mergedDisabledRef:{value:!1},b=x(()=>c.value||e.disabled);function _(f){const{onClick:T}=e;T&&T(f)}function k(f){b.value||(l.doSelect(e.internalKey,e.tmNode.rawNode),_(f))}return{mergedClsPrefix:v,dropdownPlacement:t.dropdownPlacement,paddingLeft:t.paddingLeft,iconMarginRight:t.iconMarginRight,maxIconSize:t.maxIconSize,activeIconSize:t.activeIconSize,mergedTheme:l.mergedThemeRef,menuProps:i,dropdownEnabled:ve(()=>e.root&&h.value&&i.mode!=="horizontal"&&!b.value),selected:ve(()=>l.mergedValueRef.value===e.internalKey),mergedDisabled:b,handleClick:k}},render(){const{mergedClsPrefix:e,mergedTheme:t,tmNode:r,menuProps:{renderLabel:l,nodeProps:a}}=this,i=a?.(r.rawNode);return s("div",Object.assign({},i,{role:"menuitem",class:[`${e}-menu-item`,i?.class]}),s(Co,{theme:t.peers.Tooltip,themeOverrides:t.peerOverrides.Tooltip,trigger:"hover",placement:this.dropdownPlacement,disabled:!this.dropdownEnabled||this.title===void 0,internalExtraClass:["menu-tooltip"]},{default:()=>l?l(r.rawNode):Y(this.title),trigger:()=>s(je,{tmNode:r,clsPrefix:e,paddingLeft:this.paddingLeft,iconMarginRight:this.iconMarginRight,maxIconSize:this.maxIconSize,activeIconSize:this.activeIconSize,selected:this.selected,title:this.title,extra:this.extra,disabled:this.mergedDisabled,icon:this.icon,onClick:this.handleClick})}))}}),Ve=Object.assign(Object.assign({},ye),{tmNode:{type:Object,required:!0},tmNodes:{type:Array,required:!0}}),Vo=ge(Ve),Do=O({name:"MenuOptionGroup",props:Ve,setup(e){const t=Ce(e),{NSubmenu:r}=t,l=x(()=>r?.mergedDisabledRef.value?!0:e.tmNode.disabled);W(xe,{paddingLeftRef:t.paddingLeft,mergedDisabledRef:l});const{mergedClsPrefixRef:a,props:i}=D(Z);return function(){const{value:v}=a,h=t.paddingLeft.value,{nodeProps:c}=i,b=c?.(e.tmNode.rawNode);return s("div",{class:`${v}-menu-item-group`,role:"group"},s("div",Object.assign({},b,{class:[`${v}-menu-item-group-title`,b?.class],style:[b?.style||"",h!==void 0?`padding-left: ${h}px;`:""]}),Y(e.title),e.extra?s(io,null," ",Y(e.extra)):null),s("div",null,e.tmNodes.map(_=>ze(_,i))))}}});function he(e){return e.type==="divider"||e.type==="render"}function Uo(e){return e.type==="divider"}function ze(e,t){const{rawNode:r}=e,{show:l}=r;if(l===!1)return null;if(he(r))return Uo(r)?s(Mo,Object.assign({key:e.key},r.props)):null;const{labelField:a}=t,{key:i,level:v,isGroup:h}=e,c=Object.assign(Object.assign({},r),{title:r.title||r[a],extra:r.titleExtra||r.extra,key:i,internalKey:i,level:v,root:v===0,isGroup:h});return e.children?e.isGroup?s(Do,ae(c,Vo,{tmNode:e,tmNodes:e.children,key:i})):s(fe,ae(c,qo,{key:i,rawNodes:r[t.childrenField],tmNodes:e.children,tmNode:e})):s(Ko,ae(c,jo,{key:i,tmNode:e}))}const De=Object.assign(Object.assign({},ye),{rawNodes:{type:Array,default:()=>[]},tmNodes:{type:Array,default:()=>[]},tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function,domId:String,virtualChildActive:{type:Boolean,default:void 0},isEllipsisPlaceholder:Boolean}),qo=ge(De),fe=O({name:"Submenu",props:De,setup(e){const t=Ce(e),{NMenu:r,NSubmenu:l}=t,{props:a,mergedCollapsedRef:i,mergedThemeRef:v}=r,h=x(()=>{const{disabled:f}=e;return l?.mergedDisabledRef.value||a.disabled?!0:f}),c=E(!1);W(Me,{paddingLeftRef:t.paddingLeft,mergedDisabledRef:h}),W(xe,null);function b(){const{onClick:f}=e;f&&f()}function _(){h.value||(i.value||r.toggleExpand(e.internalKey),b())}function k(f){c.value=f}return{menuProps:a,mergedTheme:v,doSelect:r.doSelect,inverted:r.invertedRef,isHorizontal:r.isHorizontalRef,mergedClsPrefix:r.mergedClsPrefixRef,maxIconSize:t.maxIconSize,activeIconSize:t.activeIconSize,iconMarginRight:t.iconMarginRight,dropdownPlacement:t.dropdownPlacement,dropdownShow:c,paddingLeft:t.paddingLeft,mergedDisabled:h,mergedValue:r.mergedValueRef,childActive:ve(()=>{var f;return(f=e.virtualChildActive)!==null&&f!==void 0?f:r.activePathRef.value.includes(e.internalKey)}),collapsed:x(()=>a.mode==="horizontal"?!1:i.value?!0:!r.mergedExpandedKeysRef.value.includes(e.internalKey)),dropdownEnabled:x(()=>!h.value&&(a.mode==="horizontal"||i.value)),handlePopoverShowChange:k,handleClick:_}},render(){var e;const{mergedClsPrefix:t,menuProps:{renderIcon:r,renderLabel:l}}=this,a=()=>{const{isHorizontal:v,paddingLeft:h,collapsed:c,mergedDisabled:b,maxIconSize:_,activeIconSize:k,title:f,childActive:T,icon:w,handleClick:g,menuProps:{nodeProps:R},dropdownShow:N,iconMarginRight:X,tmNode:j,mergedClsPrefix:$,isEllipsisPlaceholder:A,extra:y}=this,z=R?.(j.rawNode);return s("div",Object.assign({},z,{class:[`${$}-menu-item`,z?.class],role:"menuitem"}),s(je,{tmNode:j,paddingLeft:h,collapsed:c,disabled:b,iconMarginRight:X,maxIconSize:_,activeIconSize:k,title:f,extra:y,showArrow:!v,childActive:T,clsPrefix:$,icon:w,hover:N,onClick:g,isEllipsisPlaceholder:A}))},i=()=>s(lo,null,{default:()=>{const{tmNodes:v,collapsed:h}=this;return h?null:s("div",{class:`${t}-submenu-children`,role:"menu"},v.map(c=>ze(c,this.menuProps)))}});return this.root?s(Io,Object.assign({size:"large",trigger:"hover"},(e=this.menuProps)===null||e===void 0?void 0:e.dropdownProps,{themeOverrides:this.mergedTheme.peerOverrides.Dropdown,theme:this.mergedTheme.peers.Dropdown,builtinThemeOverrides:{fontSizeLarge:"14px",optionIconSizeLarge:"18px"},value:this.mergedValue,disabled:!this.dropdownEnabled,placement:this.dropdownPlacement,keyField:this.menuProps.keyField,labelField:this.menuProps.labelField,childrenField:this.menuProps.childrenField,onUpdateShow:this.handlePopoverShowChange,options:this.rawNodes,onSelect:this.doSelect,inverted:this.inverted,renderIcon:r,renderLabel:l}),{default:()=>s("div",{class:`${t}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},a(),this.isHorizontal?null:i())}):s("div",{class:`${t}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},a(),i())}}),Go=Object.assign(Object.assign({},U.props),{options:{type:Array,default:()=>[]},collapsed:{type:Boolean,default:void 0},collapsedWidth:{type:Number,default:48},iconSize:{type:Number,default:20},collapsedIconSize:{type:Number,default:24},rootIndent:Number,indent:{type:Number,default:32},labelField:{type:String,default:"label"},keyField:{type:String,default:"key"},childrenField:{type:String,default:"children"},disabledField:{type:String,default:"disabled"},defaultExpandAll:Boolean,defaultExpandedKeys:Array,expandedKeys:Array,value:[String,Number],defaultValue:{type:[String,Number],default:null},mode:{type:String,default:"vertical"},watchProps:{type:Array,default:void 0},disabled:Boolean,show:{type:Boolean,default:!0},inverted:Boolean,"onUpdate:expandedKeys":[Function,Array],onUpdateExpandedKeys:[Function,Array],onUpdateValue:[Function,Array],"onUpdate:value":[Function,Array],expandIcon:Function,renderIcon:Function,renderLabel:Function,renderExtra:Function,dropdownProps:Object,accordion:Boolean,nodeProps:Function,dropdownPlacement:{type:String,default:"bottom"},responsive:Boolean,items:Array,onOpenNamesChange:[Function,Array],onSelect:[Function,Array],onExpandedNamesChange:[Function,Array],expandedNames:Array,defaultExpandedNames:Array}),Yo=O({name:"Menu",inheritAttrs:!1,props:Go,setup(e){const{mergedClsPrefixRef:t,inlineThemeDisabled:r}=ne(e),l=U("Menu","-menu",Fo,uo,e,t),a=D($e,null),i=x(()=>{var m;const{collapsed:C}=e;if(C!==void 0)return C;if(a){const{collapseModeRef:o,collapsedRef:p}=a;if(o.value==="width")return(m=p.value)!==null&&m!==void 0?m:!1}return!1}),v=x(()=>{const{keyField:m,childrenField:C,disabledField:o}=e;return de(e.items||e.options,{getIgnored(p){return he(p)},getChildren(p){return p[C]},getDisabled(p){return p[o]},getKey(p){var P;return(P=p[m])!==null&&P!==void 0?P:p.name}})}),h=x(()=>new Set(v.value.treeNodes.map(m=>m.key))),{watchProps:c}=e,b=E(null);c?.includes("defaultValue")?Se(()=>{b.value=e.defaultValue}):b.value=e.defaultValue;const _=re(e,"value"),k=me(_,b),f=E([]),T=()=>{f.value=e.defaultExpandAll?v.value.getNonLeafKeys():e.defaultExpandedNames||e.defaultExpandedKeys||v.value.getPath(k.value,{includeSelf:!1}).keyPath};c?.includes("defaultExpandedKeys")?Se(T):T();const w=So(e,["expandedNames","expandedKeys"]),g=me(w,f),R=x(()=>v.value.treeNodes),N=x(()=>v.value.getPath(k.value).keyPath);W(Z,{props:e,mergedCollapsedRef:i,mergedThemeRef:l,mergedValueRef:k,mergedExpandedKeysRef:g,activePathRef:N,mergedClsPrefixRef:t,isHorizontalRef:x(()=>e.mode==="horizontal"),invertedRef:re(e,"inverted"),doSelect:X,toggleExpand:$});function X(m,C){const{"onUpdate:value":o,onUpdateValue:p,onSelect:P}=e;p&&L(p,m,C),o&&L(o,m,C),P&&L(P,m,C),b.value=m}function j(m){const{"onUpdate:expandedKeys":C,onUpdateExpandedKeys:o,onExpandedNamesChange:p,onOpenNamesChange:P}=e;C&&L(C,m),o&&L(o,m),p&&L(p,m),P&&L(P,m),f.value=m}function $(m){const C=Array.from(g.value),o=C.findIndex(p=>p===m);if(~o)C.splice(o,1);else{if(e.accordion&&h.value.has(m)){const p=C.findIndex(P=>h.value.has(P));p>-1&&C.splice(p,1)}C.push(m)}j(C)}const A=m=>{const C=v.value.getPath(m??k.value,{includeSelf:!1}).keyPath;if(!C.length)return;const o=Array.from(g.value),p=new Set([...o,...C]);e.accordion&&h.value.forEach(P=>{p.has(P)&&!C.includes(P)&&p.delete(P)}),j(Array.from(p))},y=x(()=>{const{inverted:m}=e,{common:{cubicBezierEaseInOut:C},self:o}=l.value,{borderRadius:p,borderColorHorizontal:P,fontSize:Je,itemHeight:Ze,dividerColor:eo}=o,n={"--n-divider-color":eo,"--n-bezier":C,"--n-font-size":Je,"--n-border-color-horizontal":P,"--n-border-radius":p,"--n-item-height":Ze};return m?(n["--n-group-text-color"]=o.groupTextColorInverted,n["--n-color"]=o.colorInverted,n["--n-item-text-color"]=o.itemTextColorInverted,n["--n-item-text-color-hover"]=o.itemTextColorHoverInverted,n["--n-item-text-color-active"]=o.itemTextColorActiveInverted,n["--n-item-text-color-child-active"]=o.itemTextColorChildActiveInverted,n["--n-item-text-color-child-active-hover"]=o.itemTextColorChildActiveInverted,n["--n-item-text-color-active-hover"]=o.itemTextColorActiveHoverInverted,n["--n-item-icon-color"]=o.itemIconColorInverted,n["--n-item-icon-color-hover"]=o.itemIconColorHoverInverted,n["--n-item-icon-color-active"]=o.itemIconColorActiveInverted,n["--n-item-icon-color-active-hover"]=o.itemIconColorActiveHoverInverted,n["--n-item-icon-color-child-active"]=o.itemIconColorChildActiveInverted,n["--n-item-icon-color-child-active-hover"]=o.itemIconColorChildActiveHoverInverted,n["--n-item-icon-color-collapsed"]=o.itemIconColorCollapsedInverted,n["--n-item-text-color-horizontal"]=o.itemTextColorHorizontalInverted,n["--n-item-text-color-hover-horizontal"]=o.itemTextColorHoverHorizontalInverted,n["--n-item-text-color-active-horizontal"]=o.itemTextColorActiveHorizontalInverted,n["--n-item-text-color-child-active-horizontal"]=o.itemTextColorChildActiveHorizontalInverted,n["--n-item-text-color-child-active-hover-horizontal"]=o.itemTextColorChildActiveHoverHorizontalInverted,n["--n-item-text-color-active-hover-horizontal"]=o.itemTextColorActiveHoverHorizontalInverted,n["--n-item-icon-color-horizontal"]=o.itemIconColorHorizontalInverted,n["--n-item-icon-color-hover-horizontal"]=o.itemIconColorHoverHorizontalInverted,n["--n-item-icon-color-active-horizontal"]=o.itemIconColorActiveHorizontalInverted,n["--n-item-icon-color-active-hover-horizontal"]=o.itemIconColorActiveHoverHorizontalInverted,n["--n-item-icon-color-child-active-horizontal"]=o.itemIconColorChildActiveHorizontalInverted,n["--n-item-icon-color-child-active-hover-horizontal"]=o.itemIconColorChildActiveHoverHorizontalInverted,n["--n-arrow-color"]=o.arrowColorInverted,n["--n-arrow-color-hover"]=o.arrowColorHoverInverted,n["--n-arrow-color-active"]=o.arrowColorActiveInverted,n["--n-arrow-color-active-hover"]=o.arrowColorActiveHoverInverted,n["--n-arrow-color-child-active"]=o.arrowColorChildActiveInverted,n["--n-arrow-color-child-active-hover"]=o.arrowColorChildActiveHoverInverted,n["--n-item-color-hover"]=o.itemColorHoverInverted,n["--n-item-color-active"]=o.itemColorActiveInverted,n["--n-item-color-active-hover"]=o.itemColorActiveHoverInverted,n["--n-item-color-active-collapsed"]=o.itemColorActiveCollapsedInverted):(n["--n-group-text-color"]=o.groupTextColor,n["--n-color"]=o.color,n["--n-item-text-color"]=o.itemTextColor,n["--n-item-text-color-hover"]=o.itemTextColorHover,n["--n-item-text-color-active"]=o.itemTextColorActive,n["--n-item-text-color-child-active"]=o.itemTextColorChildActive,n["--n-item-text-color-child-active-hover"]=o.itemTextColorChildActiveHover,n["--n-item-text-color-active-hover"]=o.itemTextColorActiveHover,n["--n-item-icon-color"]=o.itemIconColor,n["--n-item-icon-color-hover"]=o.itemIconColorHover,n["--n-item-icon-color-active"]=o.itemIconColorActive,n["--n-item-icon-color-active-hover"]=o.itemIconColorActiveHover,n["--n-item-icon-color-child-active"]=o.itemIconColorChildActive,n["--n-item-icon-color-child-active-hover"]=o.itemIconColorChildActiveHover,n["--n-item-icon-color-collapsed"]=o.itemIconColorCollapsed,n["--n-item-text-color-horizontal"]=o.itemTextColorHorizontal,n["--n-item-text-color-hover-horizontal"]=o.itemTextColorHoverHorizontal,n["--n-item-text-color-active-horizontal"]=o.itemTextColorActiveHorizontal,n["--n-item-text-color-child-active-horizontal"]=o.itemTextColorChildActiveHorizontal,n["--n-item-text-color-child-active-hover-horizontal"]=o.itemTextColorChildActiveHoverHorizontal,n["--n-item-text-color-active-hover-horizontal"]=o.itemTextColorActiveHoverHorizontal,n["--n-item-icon-color-horizontal"]=o.itemIconColorHorizontal,n["--n-item-icon-color-hover-horizontal"]=o.itemIconColorHoverHorizontal,n["--n-item-icon-color-active-horizontal"]=o.itemIconColorActiveHorizontal,n["--n-item-icon-color-active-hover-horizontal"]=o.itemIconColorActiveHoverHorizontal,n["--n-item-icon-color-child-active-horizontal"]=o.itemIconColorChildActiveHorizontal,n["--n-item-icon-color-child-active-hover-horizontal"]=o.itemIconColorChildActiveHoverHorizontal,n["--n-arrow-color"]=o.arrowColor,n["--n-arrow-color-hover"]=o.arrowColorHover,n["--n-arrow-color-active"]=o.arrowColorActive,n["--n-arrow-color-active-hover"]=o.arrowColorActiveHover,n["--n-arrow-color-child-active"]=o.arrowColorChildActive,n["--n-arrow-color-child-active-hover"]=o.arrowColorChildActiveHover,n["--n-item-color-hover"]=o.itemColorHover,n["--n-item-color-active"]=o.itemColorActive,n["--n-item-color-active-hover"]=o.itemColorActiveHover,n["--n-item-color-active-collapsed"]=o.itemColorActiveCollapsed),n}),z=r?ie("menu",x(()=>e.inverted?"a":"b"),y,e):void 0,K=co(),F=E(null),le=E(null);let B=!0;const Ie=()=>{var m;B?B=!1:(m=F.value)===null||m===void 0||m.sync({showAllItemsBeforeCalculate:!0})};function Ue(){return document.getElementById(K)}const ee=E(-1);function qe(m){ee.value=e.options.length-m}function Ge(m){m||(ee.value=-1)}const Ye=x(()=>{const m=ee.value;return{children:m===-1?[]:e.options.slice(m)}}),We=x(()=>{const{childrenField:m,disabledField:C,keyField:o}=e;return de([Ye.value],{getIgnored(p){return he(p)},getChildren(p){return p[m]},getDisabled(p){return p[C]},getKey(p){var P;return(P=p[o])!==null&&P!==void 0?P:p.name}})}),Xe=x(()=>de([{}]).treeNodes[0]);function Qe(){var m;if(ee.value===-1)return s(fe,{root:!0,level:0,key:"__ellpisisGroupPlaceholder__",internalKey:"__ellpisisGroupPlaceholder__",title:"···",tmNode:Xe.value,domId:K,isEllipsisPlaceholder:!0});const C=We.value.treeNodes[0],o=N.value,p=!!(!((m=C.children)===null||m===void 0)&&m.some(P=>o.includes(P.key)));return s(fe,{level:0,root:!0,key:"__ellpisisGroup__",internalKey:"__ellpisisGroup__",title:"···",virtualChildActive:p,tmNode:C,domId:K,rawNodes:C.rawNode.children||[],tmNodes:C.children||[],isEllipsisPlaceholder:!0})}return{mergedClsPrefix:t,controlledExpandedKeys:w,uncontrolledExpanededKeys:f,mergedExpandedKeys:g,uncontrolledValue:b,mergedValue:k,activePath:N,tmNodes:R,mergedTheme:l,mergedCollapsed:i,cssVars:r?void 0:y,themeClass:z?.themeClass,overflowRef:F,counterRef:le,updateCounter:()=>{},onResize:Ie,onUpdateOverflow:Ge,onUpdateCount:qe,renderCounter:Qe,getCounter:Ue,onRender:z?.onRender,showOption:A,deriveResponsiveState:Ie}},render(){const{mergedClsPrefix:e,mode:t,themeClass:r,onRender:l}=this;l?.();const a=()=>this.tmNodes.map(c=>ze(c,this.$props)),v=t==="horizontal"&&this.responsive,h=()=>s("div",so(this.$attrs,{role:t==="horizontal"?"menubar":"menu",class:[`${e}-menu`,r,`${e}-menu--${t}`,v&&`${e}-menu--responsive`,this.mergedCollapsed&&`${e}-menu--collapsed`],style:this.cssVars}),v?s(yo,{ref:"overflowRef",onUpdateOverflow:this.onUpdateOverflow,getCounter:this.getCounter,onUpdateCount:this.onUpdateCount,updateCounter:this.updateCounter,style:{width:"100%",display:"flex",overflow:"hidden"}},{default:a,counter:this.renderCounter}):a());return v?s(ao,{onResize:this.onResize},{default:h}):h()}}),Wo={class:"sider-inner"},Xo={key:0,class:"brand-name"},Qo=["title"],Jo={class:"page-title"},Zo=["aria-label","title"],et={class:"content-inner"},ot=O({__name:"AdminLayout",setup(e){const t=vo(),r=mo(),l=bo(),a=xo(),i=E(!1),v=window.matchMedia("(max-width: 768px)");function h(w){i.value=w.matches}ho(()=>{i.value=v.matches,v.addEventListener?.("change",h)}),fo(()=>v.removeEventListener?.("change",h));function c(w){return()=>s("span",{class:"menu-icon","aria-hidden":"true"},w)}const b=[{label:()=>s(se,{to:"/admin"},{default:()=>"仪表盘"}),key:"/admin",icon:c("📊")},{label:()=>s(se,{to:"/admin/accounts"},{default:()=>"账号"}),key:"/admin/accounts",icon:c("👤")},{label:()=>s(se,{to:"/admin/settings"},{default:()=>"设置"}),key:"/admin/settings",icon:c("⚙️")}],_=x(()=>l.path);function k(w){w!==l.path&&a.push(w)}const f=x(()=>{switch(l.name){case"admin-accounts":return"账号管理";case"admin-settings":return"系统设置";default:return"仪表盘"}});async function T(){await t.logout(),await a.push("/admin/login")}return(w,g)=>{const R=po("router-view");return ce(),go(H(ke),{class:"admin-layout","has-sider":""},{default:q(()=>[V(H(Lo),{class:"admin-sider",bordered:"","collapse-mode":"width",width:220,"collapsed-width":64,collapsed:i.value},{default:q(()=>[M("div",Wo,[M("div",{class:Re(["brand",{collapsed:i.value}])},[g[2]||(g[2]=M("span",{class:"brand-logo"},"🎓",-1)),i.value?Te("",!0):(ce(),Pe("span",Xo,"管理后台"))],2),V(H(Yo),{options:b,value:_.value,collapsed:i.value,"collapsed-width":64,"collapsed-icon-size":20,"onUpdate:value":k},null,8,["value","collapsed"]),M("div",{class:Re(["sider-footer",{collapsed:i.value}])},[i.value?Te("",!0):(ce(),Pe("div",{key:0,class:"user-name",title:H(t).me?.username??""}," 👤 "+oe(H(t).me?.username),9,Qo)),V(H(Ne),{quaternary:"",size:"small",block:!i.value,title:i.value?"退出登录":void 0,onClick:T},{default:q(()=>[Ae(oe(i.value?"⏻":"退出登录"),1)]),_:1},8,["block","title"])],2)])]),_:1},8,["collapsed"]),V(H(ke),null,{default:q(()=>[V(H(Ho),{class:"topbar",bordered:""},{default:q(()=>[M("button",{class:"icon-btn",type:"button","aria-label":"切换侧边栏",title:"切换侧边栏",onClick:g[0]||(g[0]=N=>i.value=!i.value)}," ≡ "),M("h1",Jo,oe(f.value),1),g[4]||(g[4]=M("div",{class:"spacer"},null,-1)),M("button",{class:"icon-btn",type:"button","aria-label":H(r).dark?"切换到浅色":"切换到深色",title:H(r).dark?"切换到浅色":"切换到深色",onClick:g[1]||(g[1]=N=>H(r).toggle())},oe(H(r).dark?"☀️":"🌙"),9,Zo),V(H(Ne),{quaternary:"",size:"small",onClick:T},{default:q(()=>[...g[3]||(g[3]=[Ae("退出",-1)])]),_:1})]),_:1}),V(H(Ao),{class:"content"},{default:q(()=>[M("div",et,[V(R)])]),_:1})]),_:1})]),_:1})}}}),at=wo(ot,[["__scopeId","data-v-c2cc88fd"]]);export{at as default};
