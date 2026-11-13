"""Inspector PDF en proceso aislado. No imprime datos ni excepciones del archivo."""
import os
import resource
import sys


def inspeccionar(path):
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject, StreamObject
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError()
    referencias = {(objid, generation) for generation, group in reader.xref.items() for objid in group if objid != 0}
    referencias |= {(objid, 0) for objid in reader.xref_objStm}
    if len(referencias) > 2000:
        raise ValueError()
    prohibidos = {"/JS", "/JavaScript", "/OpenAction", "/AA", "/A", "/Launch", "/EmbeddedFiles", "/EF", "/XFA", "/RichMedia", "/URI", "/SubmitForm", "/ImportData", "/GoToR"}
    vistos = set()
    presupuesto, bytes_stream = 0, 0
    def recorrer(value, nivel=0):
        nonlocal presupuesto, bytes_stream
        presupuesto += 1
        if nivel > 64 or presupuesto > 20000:
            raise ValueError()
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in vistos:
                return
            vistos.add(key)
            return recorrer(value.get_object(), nivel+1)
        if isinstance(value, DictionaryObject):
            if prohibidos & set(value) or str(value.get("/Type")) == "/EmbeddedFile":
                raise ValueError()
            if isinstance(value, StreamObject):
                data = value.get_data()
                bytes_stream += len(data)
                if bytes_stream > 16*1024*1024:
                    raise ValueError()
            for child in value.values():
                recorrer(child, nivel+1)
        elif isinstance(value, ArrayObject):
            for child in value:
                recorrer(child, nivel+1)
    recorrer(reader.trailer)
    for objid, generation in referencias:
        recorrer(IndirectObject(objid, generation, reader))
    for page in reader.pages:
        box = page.mediabox
        if not 0 < float(box.width) <= 20000 or not 0 < float(box.height) <= 20000:
            raise ValueError()


if __name__ == "__main__":
    try:
        inspeccionar(sys.argv[1])
    except BaseException:
        os._exit(2)
    print("PDF_VALIDO")
