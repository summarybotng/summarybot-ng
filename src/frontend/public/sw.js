// Service Worker for SummaryBot PWA
// Handles share target functionality
// Version: 2 - Fixed IndexedDB handling

const CACHE_NAME = 'summarybot-v2';
const SW_VERSION = '4.0.0';

// Install event - cache essential assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker');
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker');
  event.waitUntil(clients.claim());
});

// Fetch event - handle share target POST requests
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Handle share target POST to /share
  if (url.pathname === '/share' && event.request.method === 'POST') {
    event.respondWith(handleShareTarget(event.request));
    return;
  }

  // For other requests, use network-first strategy
  // Only intercept same-origin navigation requests
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(async () => {
        const cached = await caches.match(event.request);
        return cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
      })
    );
    return;
  }

  // Don't intercept other requests - let browser handle them normally
});

async function handleShareTarget(request) {
  console.log('[SW v' + SW_VERSION + '] handleShareTarget called');
  try {
    const formData = await request.formData();
    const file = formData.get('file');
    const title = formData.get('title') || '';
    const text = formData.get('text') || '';

    console.log('[SW] Share target received:', {
      hasFile: !!file,
      fileName: file?.name,
      fileSize: file?.size,
      fileType: file?.type,
      title,
      text
    });

    // Store the shared file in IndexedDB for the page to pick up
    if (file) {
      console.log('[SW] Storing file to IndexedDB...');
      await storeSharedFile(file);
      console.log('[SW] File stored successfully, redirecting...');
    } else {
      console.log('[SW] No file received in share target');
    }

    // Redirect to the share handler page
    return Response.redirect('/share-received', 303);
  } catch (error) {
    console.error('[SW] Share target error:', error);
    console.error('[SW] Error stack:', error.stack);
    return Response.redirect('/share-received?error=' + encodeURIComponent(error.message), 303);
  }
}

async function storeSharedFile(file) {
  // Open IndexedDB
  const db = await openDB();

  // Read file as ArrayBuffer
  const buffer = await file.arrayBuffer();

  // Store in IndexedDB with proper promise handling
  return new Promise((resolve, reject) => {
    const tx = db.transaction('sharedFiles', 'readwrite');
    const store = tx.objectStore('sharedFiles');

    const request = store.put({
      id: 'pending',
      name: file.name,
      type: file.type,
      size: file.size,
      data: buffer,
      timestamp: Date.now()
    });

    request.onsuccess = () => {
      console.log('[SW] Stored shared file:', file.name);
      resolve();
    };

    request.onerror = () => {
      console.error('[SW] Failed to store shared file:', request.error);
      reject(request.error);
    };

    tx.oncomplete = () => {
      console.log('[SW] IndexedDB transaction complete');
    };

    tx.onerror = () => {
      console.error('[SW] IndexedDB transaction error:', tx.error);
      reject(tx.error);
    };
  });
}

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('SummaryBotShare', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('sharedFiles')) {
        db.createObjectStore('sharedFiles', { keyPath: 'id' });
      }
    };
  });
}
