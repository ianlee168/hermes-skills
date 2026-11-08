# 浏览器内取证代码片段（复制即用）

一个调用里跑完「装 hook → 触发 → 读证据」。`browser_exec` 的 `js()` 每次都要自执行函数，返回字符串。

## 1. 装拦截器（reload 后失效，必须重装）

```python
js("""(function(){
 window.__errs=[]; window.__resp=[];
 window.addEventListener('error',e=>window.__errs.push('ERR:'+e.message+' @'+(e.filename||'')+':'+e.lineno));
 window.addEventListener('unhandledrejection',e=>window.__errs.push('REJ:'+(e.reason&&e.reason.message||e.reason)));
 const oe=console.error; console.error=function(){window.__errs.push('CE:'+Array.from(arguments).map(String).join(' ')); return oe.apply(console,arguments)};
 const of_=window.fetch; window.fetch=function(){ const u=(arguments[0]&&arguments[0].url)||arguments[0];
   const p=of_.apply(window,arguments);
   p.then(r=>{ r.clone().text().then(t=>window.__resp.push({src:'fetch',url:String(u),status:r.status,body:t.slice(0,600)})).catch(()=>{}); return r });
   return p };
 const ox=XMLHttpRequest.prototype.open, os=XMLHttpRequest.prototype.send;
 XMLHttpRequest.prototype.open=function(m,u){ this.__m=m; this.__u=u; return ox.apply(this,arguments) };
 XMLHttpRequest.prototype.send=function(){ this.addEventListener('loadend',()=>{
   window.__resp.push({src:'xhr',url:String(this.__u),status:this.status,body:String(this.responseText||'').slice(0,600)}) });
   return os.apply(this,arguments) };
 return 'installed'
})()""")
```

只关心某个接口就加过滤：`if(/checkout|trade|pay/.test(String(this.__u)))`。

## 2. 读证据

```python
print(js("JSON.stringify((window.__resp||[]).slice(-5))"))
print(js("JSON.stringify((window.__errs||[]).slice(-10))"))
print(js("document.body.innerText.slice(-400)"))   # toast 通常堆在末尾
```

中文 message 在 JSON 里是 `\uXXXX`，`json.loads` 后自然还原，别硬读转义串。

## 3. 点弹窗按钮：用选择器，不用文本

```python
js("document.querySelector('.modal-btn.confirm-btn').click()")
js("document.querySelector('.modal-btn.cancel-btn')||document.querySelector('.modal-close')")
```

通用文本匹配会命中页面里同名元素（例：「取消订单」被当成「取消」）。

## 4. 强制重载 SPA

```python
goto_url(url); time.sleep(1); js('location.reload()'); time.sleep(7)
```

同域只换 hash 不会重载；旧弹窗/旧文案会污染判断。

## 5. 资源加载是否真失败

```python
js("JSON.stringify(performance.getEntriesByType('resource').filter(r=>r.transferSize===0&&r.decodedBodySize===0).map(r=>r.name).slice(0,15))")
js("performance.getEntriesByType('resource').length")
```

`transferSize===0` 含缓存命中，单看会误报「被拦截」。真正的失败要配合控制台报错或 `responseStatus` 判断。

## 6. 已登录站点里直连 API（只读探测）

```python
# 先看 token 存在哪、长什么样
js("(()=>{const u=JSON.parse(localStorage.getItem('app-user')); return Object.keys(u).join(',')+' | '+(u.token||'').slice(0,12)})()")
# 带 token 探测；路径猜两次 404 就停，改从 __resp 里抄真实 endpoint
js("""(async () => {
 const t=JSON.parse(localStorage.getItem('app-user')).token;
 const r=await fetch('/api/xxx',{headers:{Authorization:t}});
 return r.status+' '+(await r.text()).slice(0,200);
})()""")
```

## 7. 截图取证

```python
p = capture_screenshot()          # 返回本地路径
vision_analyze(image_url=p, question='页面显示什么？有报错文字/二维码吗？')
```

卡住的「加载中…」遮罩本身就是证据：说明请求挂着或前端在等一个永远不来的 data。
