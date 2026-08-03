import sys
import re
from pathlib import Path
import subprocess
import json


def scale_number(value, scale):
    try:
        return str(round(float(value) * scale, 2))
    except ValueError:
        return value


def scale_clip(match, sx, sy):

    prefix = match.group(1)
    values = match.group(2).split(",")

    if len(values) == 4:
        values[0] = scale_number(values[0], sx)
        values[1] = scale_number(values[1], sy)
        values[2] = scale_number(values[2], sx)
        values[3] = scale_number(values[3], sy)

    return "\\" + prefix + "(" + ",".join(values) + ")"


def scale_drawings_in_line(line,sx,sy):

    if not re.search(r"\\p\d+", line):
        return line

    parts=re.split(r"(\\p\d+)", line)

    for i in range(1,len(parts)):
        drawing = parts[i]

        drawing = re.sub(
            r"(\d+\.?\d*)[ ]+(\d+\.?\d*)",
            lambda m:
                f"{float(m.group(1))*sx:.2f} {float(m.group(2))*sy:.2f}",
            drawing
        )

        parts[i]=drawing

    return "\\p".join(parts)

def scale_transforms(text, sx, sy):

    result = []
    i = 0

    while i < len(text):

        # Find \t(
        if text.startswith(r"\t(", i):

            start = i
            i += 3   # skip \t(

            depth = 1

            while i < len(text) and depth > 0:

                if text[i] == "(":
                    depth += 1

                elif text[i] == ")":
                    depth -= 1

                i += 1

            # Include closing )
            transform = text[start:i]

            # Remove \t(
            inner = transform[3:-1]

            # Scale tags inside transform
            inner = re.sub(
                r"\\(fs|bord|shad|fsp|be|blur|xbord|ybord|xshad|yshad)([+-]?\d+\.?\d*)",
                lambda m: scale_override_tag(m, sx, sy),
                inner
            )

            # Scale positions inside transform
            inner = scale_positions(inner, sx, sy)

            inner = re.sub(
                r"\\(i?clip)\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)\)",
                lambda m: scale_clip(m,sx,sy),
                inner
            )

            result.append(
                r"\t(" + inner + ")"
            )

        else:
            result.append(text[i])
            i += 1

    return "".join(result)


def scale_override_tag(match, sx, sy):

    tag = match.group(1)
    value = float(match.group(2))

    if tag in ["xbord", "xshad"]:
        value *= sx

    elif tag in ["ybord", "yshad"]:
        value *= sy

    else:
        value *= sy

    return "\\" + tag + str(round(value,2))


def scale_positions(text, sx, sy):
    r"""
    Scale:
    \pos(x,y)
    \move(x1,y1,x2,y2)
    \org(x,y)
    """

    def pos(match):
        x, y = match.groups()
        return (
            f"\\pos("
            f"{scale_number(x,sx)},"
            f"{scale_number(y,sy)})"
        )

    text = re.sub(
        r"\\pos\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)\)",
        pos,
        text
    )


    def org(match):
        x, y = match.groups()
        return (
            f"\\org("
            f"{scale_number(x,sx)},"
            f"{scale_number(y,sy)})"
        )

    text = re.sub(
        r"\\org\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)\)",
        org,
        text
    )


    def move(match):
        values = list(match.groups())

        values[0] = scale_number(values[0], sx)
        values[1] = scale_number(values[1], sy)
        values[2] = scale_number(values[2], sx)
        values[3] = scale_number(values[3], sy)

        return "\\move(" + ",".join(
            v for v in values if v is not None
        ) + ")"

    text = re.sub(
        r"\\(i?clip)\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)\)",
        lambda m:
            "\\" + m.group(1) + "(" +
            ",".join([
                scale_number(m.group(2),sx),
                scale_number(m.group(3),sy),
                scale_number(m.group(4),sx),
                scale_number(m.group(5),sy)
            ]) +
            ")",
        text
    )


    text = re.sub(
        r"\\move\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)(?:,([+-]?\d+\.?\d*),([+-]?\d+\.?\d*))?\)",
        move,
        text
    )

    return text



def resample_ass(
    input_file,
    output_file,
    new_width,
    new_height
):

    text = Path(input_file).read_text(
        encoding="utf-8-sig"
    )

    if "ScaledBorderAndShadow:" not in text:
        text=text.replace(
            "[Script Info]",
            "[Script Info]\nScaledBorderAndShadow: yes"
        )

    # Find original resolution

    old_x = re.search(
        r"PlayResX:\s*(\d+)",
        text
    )

    old_y = re.search(
        r"PlayResY:\s*(\d+)",
        text
    )


    if not old_x or not old_y:
        raise Exception(
            "Could not find PlayResX/Y"
        )


    old_width = int(old_x.group(1))
    old_height = int(old_y.group(1))


    sx = new_width / old_width
    sy = new_height / old_height


    print(
        f"Scaling {old_width}x{old_height} "
        f"-> {new_width}x{new_height}"
    )

    print(
        f"Scale factors X={sx} Y={sy}"
    )

    # Update resolution

    text = re.sub(
        r"PlayResX:\s*\d+",
        f"PlayResX: {new_width}",
        text
    )

    text = re.sub(
        r"PlayResY:\s*\d+",
        f"PlayResY: {new_height}",
        text
    )

    output_lines = []


    for line in text.splitlines():

        # Styles
        if line.startswith("Style:"):
            parts=line.split(",")

            if len(parts)>=23:

                sx2=sx
                sy2=sy

                parts[2]=scale_number(parts[2],sy2)
                
                parts[16]=scale_number(parts[16],sy2)
                parts[17]=scale_number(parts[17],sy2)

                parts[19]=scale_number(parts[19],sx2)
                parts[20]=scale_number(parts[20],sx2)
                parts[21]=scale_number(parts[21],sy2)

            line=",".join(parts)


        # Dialogue lines

        elif line.startswith(("Dialogue:", "Comment:")):

            # Scale inline tags

            line = re.sub(
                r"\\(fs|bord|shad|fsp|be|blur|xbord|ybord|xshad|yshad)([+-]?\d+\.?\d*)",
                lambda m: scale_override_tag(m,sx,sy),
                line
            )


            line = scale_positions(
                line,
                sx,
                sy
            )

            line = scale_transforms(line,sx,sy)

            line = re.sub(
                r"\\(i?clip)\(([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*),([+-]?\d+\.?\d*)\)",
                lambda m:
                    scale_clip(m,sx,sy),
                line
            )

            line = re.sub(
                r"\\pbo([+-]?\d+\.?\d*)",
                lambda m:
                    "\\pbo" + scale_number(m.group(1),sy),
                line
            )

            line = scale_drawings_in_line(line,sx,sy)


        output_lines.append(line)


    Path(output_file).write_text(
        "\n".join(output_lines),
        encoding="utf-8-sig"
    )

def get_video_resolution(video_file):
    cmd = [
        "D:\\Users\\RyanDesktop\\Documents\\vapoursynth-portable\\ffprobe.exe",
        "-v",
        "quiet",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        video_file
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    print("return code:", result.returncode)

    if result.returncode != 0:
        raise Exception("ffprobe failed")

    data = json.loads(result.stdout)

    stream = data["streams"][0]

    return (
        int(stream["width"]),
        int(stream["height"])
    )

if __name__ == "__main__":

    if len(sys.argv) != 4:
        print("Usage:")
        print("ass_resampler.py input.ass output.ass video.mp4")
        sys.exit(1)

    input_ass = sys.argv[1]
    output_ass = sys.argv[2]
    video = sys.argv[3]

    width, height = get_video_resolution(video)

    resample_ass(
        input_ass,
        output_ass,
        width,
        height
    )

    print("Finished")