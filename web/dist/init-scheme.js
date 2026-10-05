// Ставит цветовую схему до первой отрисовки, чтобы не мигало. Внешний файл: CSP страницы запрещает inline-скрипты.
try {
  var stored = localStorage.getItem('pi-planner-color-scheme');
  var scheme = stored === 'light' || stored === 'dark'
    ? stored
    : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'dark');
  document.documentElement.setAttribute('data-mantine-color-scheme', scheme);
  var theme = localStorage.getItem('pi-planner-app-theme');
  if (theme && theme !== 'default') document.documentElement.setAttribute('data-app-theme', theme);
} catch (e) {
  document.documentElement.setAttribute('data-mantine-color-scheme', 'dark');
}
