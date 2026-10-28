"""Original minimal vector scores and Type3 glyphs, generated without font assets.

The handmade notehead, clef, accidental and time-digit outlines below are test
artwork under the repository's MIT license. ToUnicode uses the SMuFL music code
points so the reader must honor PDF text matrices and font mappings.
"""

import re


def build_vector_score_pdf(*, tonic: str = "C4", clef: str = "treble", scale: float = 1.0,
                           offset_x: float = 0.0, offset_y: float = 0.0,
                           time_signature: tuple[int, int] = (4, 4)) -> bytes:
    """Build one original bar containing a sustained major triad.

    C4/treble and F2/bass exercise different pitches, clefs and key signatures;
    scale and offsets are an actual page CTM, not edits to parser test objects.
    """
    if tonic not in ("C4", "F2") or clef not in ("treble", "bass") or time_signature not in ((4, 4), (2, 4)):
        raise ValueError("Fixture supports C4/F2, treble/bass and 4/4 or 2/4.")
    if not .5 <= scale <= 2 or min(offset_x, offset_y) < 0:
        raise ValueError("Fixture scale/offset bounds exceeded.")
    objects: list[bytes] = [b"", b"", b""]

    def add(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    def stream(value: bytes) -> int:
        return add(b"<< /Length " + str(len(value)).encode() + b" >>\nstream\n" + value + b"\nendstream")

    # Independent simple vector artwork. No music-font program is embedded.
    clef_g = b"700 0 -200 -400 1000 1400 d1 45 w 200 -250 m 200 1000 l S 200 350 m -50 300 -20 -80 240 -80 c 500 -80 500 400 180 430 c -80 470 80 800 250 1050 c S"
    clef_f = b"700 0 -200 -400 1000 1400 d1 45 w 0 100 m 500 500 500 -200 0 -350 c S 600 150 45 45 re f 600 -100 45 45 re f"
    head = b"700 0 -200 -400 1000 1400 d1 0 0 m 0 180 430 180 430 0 c 430 -180 0 -180 0 0 c h 75 0 m 75 95 355 95 355 0 c 355 -95 75 -95 75 0 c h f*"
    four = b"700 0 -200 -400 1000 1400 d1 55 w 350 0 m 350 700 l 0 180 l 500 180 l S"
    two = b"700 0 -200 -400 1000 1400 d1 55 w 0 550 m 200 950 650 500 250 250 c 0 0 l 500 0 l S"
    flat = b"700 0 -200 -400 1000 1400 d1 45 w 40 -180 m 40 700 l S 40 80 m 450 500 450 -50 40 -180 c S"
    mapping = {33: ("\ue050", clef_g), 34: ("\ue0a2", head), 35: ("\ue084", four),
               36: ("\ue260", flat), 37: ("\ue062", clef_f), 38: ("\ue0a3", head), 39: ("\ue082", two)}
    procedures = {code: stream(art) for code, (_, art) in mapping.items()}
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /OriginalMusicUnicode def /CMapType 2 def\n"
            "1 begincodespacerange <00> <FF> endcodespacerange\n"
            + str(len(mapping)) + " beginbfchar\n"
            + "\n".join(f"<{code:02X}> <{ord(char):04X}>" for code, (char, _) in mapping.items())
            + "\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end").encode()
    cmap_id = stream(cmap)
    char_procs = " ".join(f"/g{code} {ref} 0 R" for code, ref in procedures.items())
    differences = " ".join(f"/g{code}" for code in mapping)
    font_id = add(("<< /Type /Font /Subtype /Type3 /Name /CustomNotation /FontBBox [-200 -400 1000 1400] "
                   "/FontMatrix [0.001 0 0 0.001 0 0] /CharProcs << " + char_procs + " >> "
                   "/Encoding << /Type /Encoding /Differences [33 " + differences + "] >> "
                   "/FirstChar 33 /LastChar 39 /Widths [700 700 700 700 700 700 700] /Resources << >> "
                   f"/ToUnicode {cmap_id} 0 R >>").encode())
    text_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    commands = [f"q {scale} 0 0 {scale} {offset_x} {offset_y} cm", ".65 w"]
    for y in (280, 285, 290, 295, 300):
        commands.append(f"50 {y} m 450 {y} l S")
    commands += ["50 280 m 50 300 l S", "450 280 m 450 300 l S"]

    def music(code: int, x: float, y: float) -> None:
        commands.append(f"BT /Music 1 Tf 20 0 0 20 {x} {y} Tm <{code:02X}> Tj ET")

    bottom_step = 30 if clef == "treble" else 18
    music(33 if clef == "treble" else 37, 55, 285 if clef == "treble" else 295)
    if tonic == "F2":
        music(36, 75, 280 + ((34 if clef == "treble" else 20) - bottom_step) * 2.5)
    music(35 if time_signature[0] == 4 else 39, 100, 295)
    music(35, 100, 285)
    match = re.fullmatch(r"([A-G])(\d)", tonic)
    assert match is not None
    root = int(match[2]) * 7 + "CDEFGAB".index(match[1])
    for step in (root, root + 2, root + 4):
        y = 280 + (step - bottom_step) * 2.5
        music(34 if time_signature == (4, 4) else 38, 210, y)
        if y < 280:
            for ledger in range(275, int(y) - 1, -5):
                commands.append(f"207 {ledger} m 222 {ledger} l S")
        elif y > 300:
            for ledger in range(305, int(y) + 1, 5):
                commands.append(f"207 {ledger} m 222 {ledger} l S")
    if time_signature == (2, 4):
        upper_y = 280 + (root + 4 - bottom_step) * 2.5
        lower_y = 280 + (root - bottom_step) * 2.5
        commands.append(f"218 {lower_y} m 218 {upper_y + 20} l S")
    commands.append("BT /Text 16 Tf 1 0 0 1 130 355 Tm (Original vector score) Tj ET Q")
    content_id = stream("\n".join(commands).encode())
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objects[2] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {500 * scale + offset_x} {400 * scale + offset_y}] "
                  f"/Resources << /Font << /Music {font_id} 0 R /Text {text_id} 0 R >> >> /Contents {content_id} 0 R >>").encode()
    document = bytearray(b"%PDF-1.4\n%original-vector-test\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(document)
