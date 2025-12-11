### Basic Concept

The **Python Column** in a **Generative Table** lets you generate or transform cell values using custom Python code, so you can build image, audio, and general-purpose transformations directly in your table.

All upstream columns (columns to the left) are passed to your code as a dictionary named `row` in the global context.

- **Keys** in `row` are column names (strings, case-sensitive).
- **Values** are the corresponding cell values for that row.

Your Python Column script should:

1. Read input values from `row` using upstream column names.
2. Process or transform those values.
3. Write the result back into `row` under **the name of the Python Column**.

Whatever you assign to `row["Python Column Name"]` becomes the value of that cell.

```python
# Read from upstream columns
value_a = row["Input Column A"]
value_b = row["Input Column B"]

# Do some processing
result = f"{value_a} - processed with {value_b}"

# Write to this column
row["Python Column Name"] = result
```

Consider using `try/except` blocks and writing fallback value when needed.

---

### Preinstalled Libraries

The following libraries are available:

- `aiohttp`
- `audioop-lts`
- `beautifulsoup4`
- `httpx`
- `matplotlib`
- `numpy`
- `opencv-python`
- `orjson`
- `pandas`
- `Pillow`
- `pyyaml`
- `regex`
- `requests`
- `ruamel.yaml`
- `scikit-image`
- `simplejson`
- `soundfile`
- `sympy`
- `tiktoken`

---

### Working with Images

When an upstream column contains an image, its value in `row` is **raw binary data** (`bytes`).

To output an image, make sure:

- The Python Column has data type `image`.
- The output image is one of: `.jpeg`, `.jpg`, `.png`, `.gif`, `.webp`.

#### Usage Pattern

1. Read image bytes from `row`.
2. Perform your image operations (for example, using a library such as Pillow / `PIL`).
3. Convert the modified image back into bytes.
4. Assign those bytes to the column.

```python
from PIL import Image
import io

# 1. Access the input image bytes by column name
image_bytes = row["Input Column Name"]

# 2. Open the bytes as a PIL Image
with Image.open(io.BytesIO(image_bytes)) as img:
    # --- perform your image processing here ---
    # Example: convert to grayscale
    img = img.convert("L")

    # 3. Save the processed image into a bytes buffer
    output_buffer = io.BytesIO()
    img.save(output_buffer, format="PNG")

    # 4. Assign the resulting bytes to the column
    row["Python Column Name"] = output_buffer.getvalue()
```

---

### Working with Audios

When an upstream column contains audio, its value in `row` is also **raw binary data** (`bytes`).

To output an audio, make sure:

- The Python Column has data type `audio`.
- The output audio is one of: `.mp3`, `.wav`.

#### Usage Pattern

1. Read audio bytes from `row`.
2. Perform your audio processing (for example, using a library such as `soundfile`).
3. Convert the processed audio back into bytes.
4. Assign those bytes to the column.

```python
import soundfile as sf
import io

# 1. Access the input audio bytes and read them
with io.BytesIO(row["Input Column Name"]) as input_buffer:
    data, samplerate = sf.read(input_buffer)

# --- perform your audio processing here ---
# Example: reduce volume by half
data = data * 0.5

# 2. Write the processed audio data to a new in-memory buffer
output_buffer = io.BytesIO()
sf.write(output_buffer, data, samplerate, format="WAV", subtype="PCM_16")

# 3. Assign the resulting bytes to the column
row["Python Column Name"] = output_buffer.getvalue()
```

---

### Making Web Requests

You can use `httpx` to make web requests. By using the appropriate column data type, you can fetch images and audios and save them in the table.

```python
import httpx
from bs4 import BeautifulSoup

# 1. Access the URL string
url = row["Input Column Name"]

# 2. Fetch the HTML content
response = httpx.get(url)

# 3. Parse the HTML with BeautifulSoup
soup = BeautifulSoup(response.text, "html.parser")

# ... perform your logic here ...
# Example: Extract the text from the first <h1> tag
extracted_text = soup.find("h1").text

# 4. Assign the extracted string to the column
# Here we assume the data type is `str`
row["Python Column Name"] = extracted_text
```
