// Sidebar toggle for mobile
document.addEventListener('DOMContentLoaded', () => {
  const burger = document.querySelector('.burger');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.overlay');

  if (burger) {
    burger.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('open');
    });
  }

  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('open');
    });
  }

  // Mark current page as active in sidebar
  const current = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.sidebar nav a').forEach(link => {
    const href = link.getAttribute('href');
    if (href === current || (current === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });
});

// Mermaid support: load and initialize Mermaid if any .mermaid blocks exist
if (document.querySelector('.mermaid')) {
  const s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
  s.onload = () => {
    try {
      if (window.mermaid && typeof mermaid.initialize === 'function') {
        mermaid.initialize({ startOnLoad: true, theme: 'neutral' });
        mermaid.init(undefined, document.querySelectorAll('.mermaid'));
      }
    } catch (e) {
      console.warn('Mermaid initialization failed', e);
    }
  };
  document.body.appendChild(s);
}
