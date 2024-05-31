const codeblock = [
	{
		type: 'output',
		regex: '<pre><code[^<]*</code></pre>',
		replace: function (text: string) {
			const language = text.match(/class="([^"]+)"/)?.[1].split(' ')?.[0] ?? ''
			return `
          <div class="pre-container">
            <div class="pre-header">
              <span>${language}</span>
              <button class="copy-code">
                <svg height="26" width="26" viewBox="0 0 22 25" fill="none" xmlns="http://www.w3.org/2000/svg" class="copy-icon">
                  <path
                    d="M14.3158 4H5.47368C4.66316 4 4 4.69545 4 5.54545V16.3636H5.47368V5.54545H14.3158V4ZM13.5789 7.09091L18 11.7273V19.4545C18 20.3045 17.3368 21 16.5263 21H8.41368C7.60316 21 6.94737 20.3045 6.94737 19.4545L6.95474 8.63636C6.95474 7.78636 7.61053 7.09091 8.42105 7.09091H13.5789ZM12.8421 12.5H16.8947L12.8421 8.25V12.5Z"
                    fill="currentColor"
                  />
                </svg>
                <svg height="20" width="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="check-icon">
                  <path
                    fill="none"
                    stroke="currentColor"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="32"
                    d="M464 128L240 384l-96-96m0 96l-96-96m320-160L232 284"
                  />
                </svg>
              </button>
            </div>
            ${text}
          </div>
        `
		}
	}
]
export default codeblock
