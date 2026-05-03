// Service Worker for SummaryBot PWA
// Handles share target functionality

const CACHE_NAME = 'summarybot-v1';

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
  try {
    const formData = await request.formData();
    const file = formData.get('file');
    const title = formData.get('title') || '';
    const text = formData.get('text') || '';

    console.log('[SW] Share target received:', {
      hasFile: !!file,
      fileName: file?.name,
      title,
      text
    });

    // Store the shared file in IndexedDB for the page to pick up
    if (file) {
      await storeSharedFile(file);
    }

    // Redirect to the share handler page
    return Response.redirect('/share-received', 303);
  } catch (error) {
    console.error('[SW] Share target error:', error);
    return Response.redirect('/share-received?error=failed', 303);
  }
}

async function storeSharedFile(file) {
  // Open IndexedDB
  const db = await openDB();

  // Read file as ArrayBuffer
  const buffer = await file.arrayBuffer();

  // Store in IndexedDB
  const tx = db.transaction('sharedFiles', 'readwrite');
  const store = tx.objectStore('sharedFiles');

  await store.put({
    id: 'pending',
    name: file.name,
    type: file.type,
    size: file.size,
    data: buffer,
    timestamp: Date.now()
  });

  console.log('[SW] Stored shared file:', file.name);
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
