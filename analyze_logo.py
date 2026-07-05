from PIL import Image
img = Image.open('/home/clement/HermesProjects/FinancialAutomation/logo.jpg')
print(f'Size: {img.size}')
print(f'Mode: {img.mode}')

# Get dominant colors by resizing + quantizing
small = img.resize((64, 64)).quantize(12)
palette = small.getpalette()
if palette:
    n_colors = len(palette) // 3
    print(f'\nDominant colors (top {min(n_colors, 12)}):')
    for i in range(min(n_colors, 12)):
        r, g, b = palette[i*3:(i+1)*3]
        print(f'  #{r:02x}{g:02x}{b:02x}  RGB({r},{g},{b})')

# Sample various regions
w, h = img.size
regions = {
    'Center': (w//2, h//2),
    'Top-left quarter': (w//4, h//4),
    'Top-right quarter': (3*w//4, h//4),
    'Bottom-left quarter': (w//4, 3*h//4),
    'Bottom-right quarter': (3*w//4, 3*h//4),
    'Top-center': (w//2, h//6),
    'Bottom-center': (w//2, 5*h//6),
}
print('\nRegion samples:')
for name, (x, y) in regions.items():
    pix = img.getpixel((x, y))
    print(f'  {name}: RGB{pix}')

# Check if there's a logo on light or dark background
# Sample the 4 corners for background color
corners = [
    img.getpixel((5, 5)),
    img.getpixel((w-5, 5)),
    img.getpixel((5, h-5)),
    img.getpixel((w-5, h-5)),
]
print(f'\nCorner colors (background): {corners}')

# Check first 100 pixels of top row for text/logo in top area
top_area = []
for x in range(50, w-50, 3):
    for y in range(30, 150, 3):
        top_area.append(img.getpixel((x, y)))
unique_top_area = set(top_area)
print(f'\nUnique colors in top area (30-150px): {len(unique_top_area)}')
# Sort by brightness
brightness = [(r+g+b, (r,g,b)) for r,g,b in unique_top_area]
brightness.sort()
# Show the most common colors
from collections import Counter
color_counts = Counter(top_area)
print('Most common colors in top area:')
for color, count in color_counts.most_common(10):
    r, g, b = color
    print(f'  RGB({r},{g},{b}) #{r:02x}{g:02x}{b:02x} - {count}px')
