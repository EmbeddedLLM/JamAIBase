module.exports = {
	packagerConfig: {
		icon: './electron/icons/icon',
		asar: true,
	},
	outDir: './build-electron',
	rebuildConfig: {},
	makers: [
		{
			name: '@electron-forge/maker-squirrel'
		},
		{
			name: '@electron-forge/maker-zip'
		},
		{
			name: '@electron-forge/maker-dmg',
			config: {
				format: 'ULFO'
			}
		},
		{
			name: '@electron-forge/maker-deb',
			config: {}
		}
		// {
		//   name: '@electron-forge/maker-rpm',
		//   config: {},
		// },
	]
};
