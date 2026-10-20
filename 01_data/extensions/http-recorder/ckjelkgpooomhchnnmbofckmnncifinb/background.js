var recordedData = [];
var lastVisitedPages = [];

// Ciclo de vida Service Worker
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

chrome.runtime.onInstalled.addListener(() => {
  console.log("HTTP Recorder instalado y activo.");
});

// Registrar solicitudes HTTP
chrome.webRequest.onCompleted.addListener(
  function(details) {
    recordedData.push(details);
  }, 
  { urls: ["<all_urls>"] }
);

// Registrar cambios de URL
chrome.tabs.onUpdated.addListener(function(tabId, changeInfo, tab) {
  if (changeInfo.url) {
    if (!changeInfo.url.startsWith("chrome://") && 
        !changeInfo.url.startsWith("chrome-extension://") && 
        !changeInfo.url.startsWith("https://welcome.adguard.com/")) {
      lastVisitedPages.push(changeInfo.url);
    }
  }
});

// Listener de mensajes para getData y getLastVisitedPage
chrome.runtime.onMessage.addListener(
  function(request, sender, sendResponse) {
    if (request.cmd === "getData") {
      sendResponse(recordedData);
    } 
    else if (request.cmd === "getLastVisitedPage") {
      sendResponse(lastVisitedPages[lastVisitedPages.length - 1]);
    }
    return true; // Mantiene el canal abierto para respuesta asincrona
  }
);