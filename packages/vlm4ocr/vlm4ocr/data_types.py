import os
from typing import List
from dataclasses import dataclass

@dataclass
class OCRResult:
    def __init__(self, input_dir:str, output_mode:str, pages:List[str]=None):
        """
        This class represents the result of an OCR process.

        Parameters:
        ----------
        input_dir : str
            The directory where the input files (e.g., image, PDF, tiff) are located.
        output_mode : str
            The output format. Must be 'markdown', 'HTML', or 'text'.
        pages : List[str]
            A list of strings, each representing a page of the OCR result.
        """
        self.input_dir = input_dir
        self.filename = os.path.basename(input_dir)

        # Check if the output_mode is valid
        if output_mode not in ["markdown", "HTML", "text"]:
            raise ValueError("output_mode must be 'markdown', 'HTML', or 'text'")
        self.output_mode = output_mode

        # Check if pages is a list of strings
        if pages is None:
            self.pages = []
        else:
            if not isinstance(pages, list):
                raise ValueError("pages must be a list of strings")
            for page in pages:
                if not isinstance(page, str):
                    raise ValueError("Each page must be a string")
        self.pages = pages

    def add_page(self, page:str):
        if isinstance(page, str):
            self.pages.append(page)
        else:
            raise ValueError("page must be a string")

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, idx):
        return self.pages[idx]
    
    def __iter__(self):
        return iter(self.pages)
    
    def to_string(self, page_delimiter:str="auto") -> str:
        """
        Convert the OCRResult object to a string representation.

        Parameters:
        ----------
        page_delimiter : str, Optional
            Only applies if separate_pages = True. The delimiter to use between PDF pages. 
            if 'auto', it will be set to the default page delimiter for the output mode: 
            'markdown' -> '\n\n---\n\n'
            'HTML' -> '<br><br>'
            'text' -> '\n\n---\n\n'
        """
        if isinstance(page_delimiter, str):
            if page_delimiter == "auto":
                if self.output_mode == "markdown":
                    self.page_delimiter = "\n\n---\n\n"
                elif self.output_mode == "HTML":
                    self.page_delimiter = "<br><br>"
                else:
                    self.page_delimiter = "\n\n---\n\n"
            else:
                self.page_delimiter = page_delimiter
        else:
            raise ValueError("page_delimiter must be a string")
        
        return self.page_delimiter.join(self.pages)