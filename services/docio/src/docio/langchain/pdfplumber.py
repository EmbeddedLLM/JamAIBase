import warnings
from typing import Any, Iterable, Iterator, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pdfplumber.page
import torch
from langchain.document_loaders.base import BaseBlobParser
from langchain.document_loaders.blob_loaders import Blob
from langchain.document_loaders.pdf import BasePDFLoader
from pydantic_settings import BaseSettings, SettingsConfigDict
from transformers import DetrFeatureExtractor, TableTransformerForObjectDetection

from jamaibase.protocol import Document


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    docio_device: str = "cpu"


config = Config()

_PDF_FILTER_WITH_LOSS = ["DCTDecode", "DCT", "JPXDecode"]
_PDF_FILTER_WITHOUT_LOSS = [
    "LZWDecode",
    "LZW",
    "FlateDecode",
    "Fl",
    "ASCII85Decode",
    "A85",
    "ASCIIHexDecode",
    "AHx",
    "RunLengthDecode",
    "RL",
    "CCITTFaxDecode",
    "CCF",
    "JBIG2Decode",
]

# Define colors for visualization
COLORS = [
    [0.000, 0.447, 0.741],
    [0.850, 0.325, 0.098],
    [0.929, 0.694, 0.125],
    [0.494, 0.184, 0.556],
    [0.466, 0.674, 0.188],
    [0.301, 0.745, 0.933],
]


def extract_from_images_with_rapidocr(
    images: Sequence[Iterable[np.ndarray] | bytes],
) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ImportError(
            "`rapidocr-onnxruntime` package not found, please install it with "
            "`pip install rapidocr-onnxruntime`"
        )
    ocr = RapidOCR()
    text = ""
    for img in images:
        result, _ = ocr(img)
        if result:
            result = [text[1] for text in result]
            text += "\n".join(result)
    return text


class PDFPlumberParser(BaseBlobParser):
    """Parse `PDF` with `PDFPlumber`."""

    def __init__(
        self,
        text_kwargs: Mapping[str, Any] | None = None,
        dedupe: bool = False,
        extract_images: bool = False,
        table_detection_conf: float = 0.7,
    ) -> None:
        """Initialize the parser.

        Args:
            text_kwargs: Keyword arguments to pass to ``pdfplumber.Page.extract_text()``
            dedupe: Avoiding the error of duplicate characters if `dedupe=True`.
        """
        self.text_kwargs = text_kwargs or {}
        self.dedupe = dedupe
        self.extract_images = extract_images

        self.feature_extractor = DetrFeatureExtractor()
        self.model = TableTransformerForObjectDetection.from_pretrained(
            "microsoft/table-transformer-detection", device_map=config.docio_device
        )

        self.table_detection_conf = table_detection_conf

    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        """Lazily parse the blob."""
        import pdfplumber

        with blob.as_bytes_io() as file_path:
            doc = pdfplumber.open(file_path)  # open document

            yield from [
                Document(
                    page_content=self._process_page_content(page)
                    + "\n"
                    + self._extract_images_from_page(page),
                    metadata=dict(
                        {
                            "source": blob.source,
                            "file_path": blob.source,
                            "page": page.page_number - 1,
                            "total_pages": len(doc.pages),
                        },
                        **{
                            k: doc.metadata[k]
                            for k in doc.metadata
                            if type(doc.metadata[k]) in [str, int]
                        },
                    ),
                )
                for page in doc.pages
                if page.chars != []  # to skip blank page (or page without any text)
            ]

    def _table_bbox_results(self, pil_img, model, scores, labels, boxes, save_file=None):
        """
        model.config.id2label: {
            0: "table",
            1: "table column",
            2: "table row",
            3: "table column header",
            4: "table projected row header",
            5: "table spanning cell",
        }
        """

        # Create a figure for visualization
        plt.figure(figsize=(16, 10))
        # plt.figure(figsize=(160, 100))
        plt.imshow(pil_img)

        # Get the current axis
        ax = plt.gca()

        # Repeat the COLORS list multiple times for visualization
        colors = COLORS * 100

        table_bboxes = []

        # Iterate through scores, labels, boxes, and colors for visualization
        for score, label, (xmin, ymin, xmax, ymax), c in zip(
            scores.tolist(), labels.tolist(), boxes.tolist(), colors
        ):
            # Add a rectangle to the image for the detected object's bounding box
            ax.add_patch(
                plt.Rectangle(
                    (xmin, ymin),
                    xmax - xmin,
                    ymax - ymin,
                    fill=False,
                    color=c,
                    linewidth=3,
                )
            )
            table_bboxes.append((xmin, ymin, xmax, ymax))

            # Prepare the text for the label and score
            # print(f"label: {label}, score: {score:0.2f}")
            text = f"{model.config.id2label[label]}: {score:0.2f}"

            # Add the label and score text to the image
            ax.text(xmin, ymin, text, fontsize=15, bbox=dict(facecolor="yellow", alpha=0.5))

        # Turn off the axis
        plt.axis("off")

        # Display the visualization
        # plt.show()
        if save_file:
            plt.savefig(save_file, bbox_inches="tight")

        plt.close()  # close the plt

        return table_bboxes

    def _process_page_content(self, page: pdfplumber.page.Page) -> str:
        image = page.to_image().original

        width, height = image.size
        # print(f"width, height: {width, height}") # (596, 808)

        encoding = self.feature_extractor(image, return_tensors="pt").to(config.docio_device)
        # Get the keys of the encoding dictionary
        # keys = encoding.keys()
        # print(f"keys: {keys}")

        # with torch.no_grad():  # to onnx
        with torch.inference_mode():  # to onnx
            outputs = self.model(**encoding)

        # Post-process the object detection outputs using the feature extractor
        results = self.feature_extractor.post_process_object_detection(
            outputs, threshold=self.table_detection_conf, target_sizes=[(height, width)]
        )[0]

        # save_detection_file = os.path.join(
        #     save_detection_dir, f"{pdf_file.split('/')[-1][:-4]}_p{i+1:03d}.png"
        # )

        # print(f"model.config.id2label: {model.config.id2label}")

        # table_bboxes = self._table_bbox_results(
        #     image,
        #     self.model,
        #     results["scores"],
        #     results["labels"],
        #     results["boxes"],
        #     # save_detection_file,
        # )
        table_bboxes = results["boxes"].tolist()
        # PDF Parsing
        pages_chars = []
        pages_words = []
        char_widths = []
        char_heights = []
        sizes = []
        full_text = ""
        for c in page.chars:
            char_widths.append(c["width"])
            char_heights.append(c["height"])
            sizes.append(c["size"])

        charW_med = np.median(np.array(char_widths))
        # charW_avg = np.sum(np.array(char_widths)) / len(char_widths)
        # print(f"char_width_median: {charW_med}")
        # print(f"char_width_avg: {charW_avg}")

        charH_med = np.median(np.array(char_heights))
        # charH_avg = np.sum(np.array(char_heights)) / len(char_heights)
        # print(f"char_height_median: {charH_med}")
        # print(f"char_height_avg: {charH_avg}")

        size_med = np.median(np.array(sizes))
        # size_avg = np.sum(np.array(sizes)) / len(sizes)
        # print(f"size_median: {size_med}")
        # print(f"size_avg: {size_avg}")

        # for i, page in enumerate(pdf.pages):
        try:
            page = page.within_bbox(bbox=(0, 0, page.width, page.height))
            # print(f"page.width, page.height: {page.width, page.height}") # (595.276, 807.874)
        except Exception:
            pass
        selected_w_info = []
        words = page.extract_words()
        for w in words:
            selected_w_info.append(
                {
                    # "page_number": i + 1,
                    "text": w["text"],
                    "size": w["bottom"] - w["top"],
                    "x0": w["x0"],
                    "x1": w["x1"],
                    "y0": page.height - w["bottom"],
                    "y1": (page.height - w["bottom"]) + (w["bottom"]) - w["top"],  # y0 + size
                    "top": w["top"],
                    "bottom": w["bottom"],
                    "doctop": w["doctop"],
                }
            )

        selected_info = []
        for c in page.chars:
            selected_info.append(
                {
                    "page_number": c["page_number"],
                    "text": c["text"],
                    "size": c["size"],
                    "adv": c["adv"],
                    #   "upright": c["upright"],
                    "height": c["height"],
                    "width": c["width"],
                    "x0": c["x0"],
                    "x1": c["x1"],
                    "y0": c["y0"],
                    "y1": c["y1"],
                    "top": c["top"],
                    "bottom": c["bottom"],
                    "doctop": c["doctop"],
                }
            )
        horizontal_bottom = selected_info[0]["bottom"]
        horizontal_top = selected_info[0]["top"]
        char_right = selected_info[0]["x1"]
        # char_left = selected_info[0]["x0"]

        table_char_idxes_groups = []

        # tmp_text = ""
        # print(f"page_tables: {table_bboxes}")

        # image bbox enlargement - based on intersection of extract_words bbox
        for j, page_table in enumerate(table_bboxes):
            # print(f"\ntable {j}")

            # (xmin, ymin) == top left (from image bbox)
            xmin, ymin, xmax, ymax = page_table

            # convert to pdf bbox
            # (xmin, ymin) == bottom left (pdf bbox)
            ymin2 = page.height - ymax
            ymax2 = 0 + ymin2 + (ymax - ymin)

            xminL, yminL, xmaxL, ymaxL = xmin, ymin2, xmax, ymax2
            # print(f"xmin, ymin2, xmax, ymax2: {xmin, ymin2, xmax, ymax2}")
            for k, w_ in enumerate(selected_w_info):
                """
                (x0, y1)     (x1, y1)
                1    ___________    2
                    |           |
                    |           |
                0   |___________|   3
                (x0, y0)     (x1, y0)
                """
                # check if either word textbbox coor inside the table bbox
                # if yes, enlarge the table bbox
                if (
                    (
                        (w_["x0"] >= xmin and w_["x0"] <= xmax)
                        and (w_["y0"] >= ymin2 and w_["y0"] <= ymax2)
                    )  # bottom left - x0, y0
                    or (
                        (w_["x0"] >= xmin and w_["x0"] <= xmax)
                        and (w_["y1"] >= ymin2 and w_["y1"] <= ymax2)
                    )  # top left - x0, y1
                    or (
                        (w_["x1"] >= xmin and w_["x1"] <= xmax)
                        and (w_["y1"] >= ymin2 and w_["y1"] <= ymax2)
                    )  # top right - x1, y1
                    or (
                        (w_["x1"] >= xmin and w_["x1"] <= xmax)
                        and (w_["y0"] >= ymin2 and w_["y0"] <= ymax2)
                    )  # bottom right - x1, y0
                ):
                    xminL = min(w_["x0"], xminL)
                    yminL = min(w_["y0"], yminL)
                    xmaxL = max(w_["x1"], xmaxL)
                    ymaxL = max(w_["y1"], ymaxL)

            # print(f"xminL, yminL, xmaxL, ymaxL: {xminL, yminL, xmaxL, ymaxL}")

            table_char_idxes = []
            xmin, ymin, xmax, ymax = xminL, yminL, xmaxL, ymaxL
            for k, c_ in enumerate(selected_info):
                # check if either char bbox coor inside the enlarged table bbox
                if (
                    (
                        (c_["x0"] >= xmin and c_["x0"] <= xmax)
                        and (c_["y0"] >= ymin2 and c_["y0"] <= ymax2)
                    )  # bottom left - x0, y0
                    or (
                        (c_["x0"] >= xmin and c_["x0"] <= xmax)
                        and (c_["y1"] >= ymin2 and c_["y1"] <= ymax2)
                    )  # top left - x0, y1
                    or (
                        (c_["x1"] >= xmin and c_["x1"] <= xmax)
                        and (c_["y1"] >= ymin2 and c_["y1"] <= ymax2)
                    )  # top right - x1, y1
                    or (
                        (c_["x1"] >= xmin and c_["x1"] <= xmax)
                        and (c_["y0"] >= ymin2 and c_["y0"] <= ymax2)
                    )  # bottom right - x1, y0
                ):
                    table_char_idxes.append(k)
                    # tmp_text += c_["text"]
            # print(f"tmp_text: {tmp_text}")
            table_char_idxes_groups.append(table_char_idxes)
        table_start_idxes = []
        table_end_idxes = []
        for table_char_idxes_group in table_char_idxes_groups:
            if len(table_char_idxes_group) > 0:
                table_start_idxes.append(table_char_idxes_group[0])
                table_end_idxes.append(table_char_idxes_group[-1])

        # print(f"table_start_idxes: {table_start_idxes}")
        # print(f"table_end_idxes: {table_end_idxes}")

        for k, c_ in enumerate(selected_info):
            if k in table_start_idxes:
                full_text += "\n<TABLE>"

            if c_["top"] > (horizontal_bottom):
                if (c_["bottom"] - horizontal_bottom) > page.height * 0.3:
                    # ex: CONTENTS
                    full_text += "\n" + c_["text"]
                # elif (c_["x0"] - char_right) > charW_med * c_["adv"] * 1.9:
                #     # next word
                #     full_text += ("" if c_["text"] == " " else " ") + c_["text"]
                elif (c_["x0"] - char_right) > charW_med * c_["adv"] * 1.9:
                    # next word
                    full_text += ("" if c_["text"] == " " else " ") + c_["text"]
                else:
                    # next paragraph
                    full_text += (
                        "\n\n" if (c_["top"] - horizontal_bottom) > charH_med * 0.8 else "\n"
                    ) + c_["text"]
            elif c_["bottom"] < horizontal_top:
                if c_["x0"] < char_right:
                    # ex: ANNUAL REPORT, Other Listed Company Directorship(s)
                    full_text += "\n\n" + c_["text"]
                else:
                    # next column
                    full_text += "\n\n" + c_["text"]
            elif c_["size"] > size_med * 1.7:  # bigger text
                # full_text += "<>"
                if (c_["x0"] - char_right) > (c_["size"] / c_["adv"]):
                    # next word
                    full_text += ("" if c_["text"] == " " else " ") + c_["text"]
                else:
                    full_text += c_["text"]  # normal next char
            elif c_["size"] < size_med * 1.3:  # smaller text
                # full_text += "<>"
                if (c_["x0"] - char_right) > charH_med * 0.2:
                    # next word
                    full_text += ("" if c_["text"] == " " else " ") + c_["text"]
                else:
                    full_text += c_["text"]  # normal next char
            # elif (c_["x0"] - char_right) > charW_med * 0.2:
            elif (c_["x0"] - char_right) > charW_med * c_["adv"] * 1.9:
                # next word
                full_text += ("" if c_["text"] == " " else " ") + c_["text"]
            else:
                full_text += c_["text"]  # normal next char

            if k in table_end_idxes:
                full_text += "\n</TABLE>"

            horizontal_bottom = c_["bottom"]
            horizontal_top = c_["top"]
            char_right = c_["x1"]
            # char_left = c_["x0"]

        pages_chars += selected_info
        pages_words += selected_w_info

        # df = pd.DataFrame.from_records(pages_chars)
        # df.to_csv("page_plumber.csv", float_format="%.2f")
        # df = pd.DataFrame.from_records(pages_words)
        # df.to_csv("page_plumber_text_words.csv", float_format="%.2f")

        return full_text

    def _extract_images_from_page(self, page: pdfplumber.page.Page) -> str:
        """Extract images from page and get the text with RapidOCR."""
        if not self.extract_images:
            return ""

        images = []
        for img in page.images:
            if img["stream"]["Filter"].name in _PDF_FILTER_WITHOUT_LOSS:
                images.append(
                    np.frombuffer(img["stream"].get_data(), dtype=np.uint8).reshape(
                        img["stream"]["Height"], img["stream"]["Width"], -1
                    )
                )
            elif img["stream"]["Filter"].name in _PDF_FILTER_WITH_LOSS:
                images.append(img["stream"].get_data())
            else:
                warnings.warn("Unknown PDF Filter!")

        return extract_from_images_with_rapidocr(images)


class PDFPlumberLoader(BasePDFLoader):
    """Load `PDF` files using `pdfplumber`."""

    def __init__(
        self,
        file_path: str,
        text_kwargs: Mapping[str, Any] | None = None,
        dedupe: bool = False,
        headers: dict | None = None,
        extract_images: bool = False,
    ) -> None:
        """Initialize with a file path."""
        try:
            import pdfplumber  # noqa:F401
        except ImportError:
            raise ImportError(
                "pdfplumber package not found, please install it with " "`pip install pdfplumber`"
            )

        super().__init__(file_path, headers=headers)
        self.text_kwargs = text_kwargs or {}
        self.dedupe = dedupe
        self.extract_images = extract_images

    def load(self) -> list[Document]:
        """Load file."""

        parser = PDFPlumberParser(
            text_kwargs=self.text_kwargs,
            dedupe=self.dedupe,
            extract_images=self.extract_images,
        )
        blob = Blob.from_path(self.file_path)
        return parser.parse(blob)
