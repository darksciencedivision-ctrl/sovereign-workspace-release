"use strict";
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("spike", {
  invoke: (ch, ...args) => ipcRenderer.invoke(ch, ...args),
  on: (ch, fn) => { const h = (_e, ...args) => fn(...args); ipcRenderer.on(ch, h); return () => ipcRenderer.removeListener(ch, h); },
});
