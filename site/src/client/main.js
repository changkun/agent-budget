// Progressive enhancement for server-rendered pages.

function confirmDeletes() {
  for (const form of document.querySelectorAll('form.delete-form')) {
    form.addEventListener('submit', (event) => {
      if (!window.confirm('Delete this book?')) event.preventDefault();
    });
  }
}

function normalizeTagInput() {
  const input = document.querySelector('input[name="tags"]');
  if (!input) return;
  input.addEventListener('blur', () => {
    input.value = input.value
      .split(',')
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean)
      .join(', ');
  });
}

document.addEventListener('DOMContentLoaded', () => {
  confirmDeletes();
  normalizeTagInput();
});
