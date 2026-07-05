from PIL import Image
from collections import Counter

img = Image.open('/home/clement/HermesProjects/FinancialAutomation/logo.jpg')
w, h = img.size

# Build a histogram of non-white/near-white pixels
# White is ~#fbfbfb - let's filter out anything with R>240 G>240 B>240
logo_pixels = []
for y in range(h):
    for x in range(w):
        r, g, b = img.getpixel((x, y))
        # Exclude near-white background
        if r < 230 or g < 230 or b < 230:
            logo_pixels.append((r, g, b))

print(f"Non-white pixels: {len(logo_pixels)} / {w*h}")

# Most common non-white colors
if logo_pixels:
    counter = Counter(logo_pixels)
    print("\nMost common non-white colors:")
    for color, count in counter.most_common(20):
        r, g, b = color
        print(f"  #{r:02x}{g:02x}{b:02x}  RGB({r},{g},{b})  {count}px")

# Check if there's specific blue tones
blue_pixels = [(r,g,b) for r,g,b in logo_pixels if b > r and b > g and b > 100]
if blue_pixels:
    blue_counter = Counter(blue_pixels)
    print(f"\nBlue pixel count: {len(blue_pixels)}")
    print("Most common blue colors:")
    for color, count in blue_counter.most_common(10):
        r, g, b = color
        print(f"  #{r:02x}{g:02x}{b:02x}  RGB({r},{g},{b})  {count}px")

# Check if there are dark colors (text, outlines)
dark_pixels = [(r,g,b) for r,g,b in logo_pixels if r < 80 and g < 80 and b < 80]
if dark_pixels:
    print(f"\nDark pixel count: {len(dark_pixels)}")
    
# Check for greens/teals that could be accent
green_pixels = [(r,g,b) for r,g,b in logo_pixels if g > r+10 and g > b+10 and g > 60]
if green_pixels:
    green_counter = Counter(green_pixels)
    print(f"\nGreen/teal pixel count: {len(green_pixels)}")
    print("Most common green/teal colors:")
    for color, count in green_counter.most_common(10):
        r, g, b = color
        print(f"  #{r:02x}{g:02x}{b:02x}  RGB({r},{g},{b})  {count}px")
