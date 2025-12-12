from PIL import Image, ImageDraw

def create_favicon():
    # Create a 256x256 image
    img = Image.new('RGBA', (256, 256), color=(0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Draw a red rounded rectangle
    d.rounded_rectangle([(0, 0), (256, 256)], radius=40, fill="#dc2626")
    
    # Draw a white chart line
    # Points scaled from 100x100 to 256x256
    points = [(50, 180), (100, 130), (150, 155), (200, 80)]
    d.line(points, fill="white", width=20, joint="curve")
    
    # Draw a dot at the end
    d.ellipse([(190, 70), (210, 90)], fill="white")
    
    # Save as ICO
    img.save("app/static/favicon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Successfully created app/static/favicon.ico")

if __name__ == "__main__":
    create_favicon()