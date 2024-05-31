import { fontFamily } from 'tailwindcss/defaultTheme';
import plugin from 'tailwindcss/plugin';
import flattenColorPalette from 'tailwindcss/lib/util/flattenColorPalette';

/** @type {import('tailwindcss').Config} */
const config = {
	darkMode: ['class'],
	content: ['./src/**/*.{html,js,svelte,ts}'],
	safelist: ['dark'],
	theme: {
		container: {
			center: true,
			padding: '2rem',
			screens: {
				'2xl': '1400px'
			}
		},
		extend: {
			colors: {
				border: 'hsl(var(--border) / <alpha-value>)',
				input: 'hsl(var(--input) / <alpha-value>)',
				ring: 'hsl(var(--ring) / <alpha-value>)',
				background: 'hsl(var(--background) / <alpha-value>)',
				foreground: 'hsl(var(--foreground) / <alpha-value>)',
				text: 'hsl(var(--text) / <alpha-value>)',
				primary: {
					DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
					foreground: 'hsl(var(--primary-foreground) / <alpha-value>)'
				},
				secondary: {
					DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
					foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)'
				},
				success: 'hsl(var(--success) / <alpha-value>)',
				warning: 'hsl(var(--warning) / <alpha-value>)',
				destructive: {
					DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
					foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)'
				},
				muted: {
					DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
					foreground: 'hsl(var(--muted-foreground) / <alpha-value>)'
				},
				accent: {
					DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
					foreground: 'hsl(var(--accent-foreground) / <alpha-value>)'
				},
				popover: {
					DEFAULT: 'hsl(var(--popover) / <alpha-value>)',
					foreground: 'hsl(var(--popover-foreground) / <alpha-value>)'
				},
				card: {
					DEFAULT: 'hsl(var(--card) / <alpha-value>)',
					foreground: 'hsl(var(--card-foreground) / <alpha-value>)'
				}
			},
			borderRadius: {
				lg: 'var(--radius)',
				md: 'calc(var(--radius) - 2px)',
				sm: 'calc(var(--radius) - 4px)'
			},
			fontFamily: {
				sans: [...fontFamily.sans]
			},
			screens: {
				xs: '320px',
				'3xl': '1800px'
			},
			height: {
				screen: ['100vh', '100dvh']
			},
			boxShadow: {
				float: '0px 0px 4px 0px rgba(0,0,0,0.25)'
			},
			keyframes: {
				blink: {
					'0%': {
						opacity: '0'
					},
					'50%': {
						opacity: '1'
					},
					'100%': {
						opacity: '0'
					}
				}
			},
			animation: {
				blink: 'blink 1060ms steps(1) infinite'
			}
		}
	},
	plugins: [
		require('@tailwindcss/container-queries'),
		plugin(function ({ addVariant, e }) {
			addVariant('data-dark', ({ modifySelectors, separator }) => {
				modifySelectors(({ className }) => {
					return `:root[data-theme="dark"] .${e(`data-dark${separator}${className}`)}`;
				});
			}); // here
		}),
		// plugin for blinking border with selection for border color
		plugin(function ({ matchUtilities, theme }) {
			matchUtilities(
				{
					'border-blink': (value) => {
						return {
							[`@keyframes blink-border`]: {
								'0%': {
									borderColor: value.replace('<alpha-value>', 1)
								},
								'50%': {
									borderColor: 'transparent'
								},
								'100%': {
									borderColor: value.replace('<alpha-value>', 1)
								}
							},
							animation: `blink-border 1s infinite`,
							borderColor: value.replace('<alpha-value>', 1)
						};
					}
				},
				{ values: flattenColorPalette(theme('colors')) }
			);
		})
	]
};

export default config;
