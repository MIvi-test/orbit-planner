import { createTheme, rem } from '@mantine/core'

/**
 * Тема «Маршрутного листа» (docs/UI_DESIGN.md §7).
 * Радиус 2 — маршрутный лист, а не карточки; акцент — почтовая синь,
 * а не дефолтный синий Mantine.
 */
export const theme = createTheme({
  primaryColor: 'post',
  primaryShade: { light: 8, dark: 6 },
  defaultRadius: 2,
  fontFamily: 'var(--font-text)',
  fontFamilyMonospace: 'var(--font-mono)',
  headings: {
    fontFamily: 'var(--font-heading)',
    sizes: {
      h1: { fontSize: rem(38), lineHeight: '1.15', fontWeight: '800' },
      h2: { fontSize: rem(27), lineHeight: '1.2', fontWeight: '600' },
      h3: { fontSize: rem(21), lineHeight: '1.3', fontWeight: '700' },
      h4: { fontSize: rem(17), lineHeight: '1.35', fontWeight: '700' },
    },
  },
  colors: {
    dark: [
      '#f3f6fc',
      '#dce4f1',
      '#a9b5cc',
      '#74839e',
      '#33415b',
      '#25324a',
      '#141b2e',
      '#0b1020',
      '#080d1a',
      '#050914',
    ],
    post: [
      '#EEF1F6',
      '#D8DFEA',
      '#B4C1D6',
      '#8DA0C0',
      '#6E85AD',
      '#5A73A1',
      '#4E6899',
      '#3F5885',
      '#14213D',
      '#0D1729',
    ],
  },
  components: {
    Paper: {
      defaultProps: { withBorder: true },
      styles: {
        root: { boxShadow: 'none' },
      },
    },
    // Дефолтный капс Mantine запрещён (UI_DESIGN §6).
    Badge: {
      styles: {
        label: { textTransform: 'none' },
      },
    },
    Table: {
      styles: {
        table: { fontVariantNumeric: 'tabular-nums' },
      },
    },
  },
})
