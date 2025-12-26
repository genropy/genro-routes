from __future__ import annotations
import io
import base64
try:
    import qrcode
except ImportError:
    qrcode = None

from genro_routes import Router, RoutingClass, route

class QRCodeService(RoutingClass):
    """Wraps the qrcode library to generate QR code assets."""
    
    def __init__(self):
        self.api = Router(self, name="qrcode").plug("pydantic")

    @route("qrcode")
    def generate_base64(self, data: str, box_size: int = 10, border: int = 4) -> str:
        """Generates a QR code and returns it as a Base64 encoded PNG string."""
        if qrcode is None:
            return "Error: 'qrcode' library not installed. Run 'pip install qrcode[pil]'"
            
        qr = qrcode.QRCode(version=1, box_size=box_size, border=border)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

if __name__ == "__main__":
    service = QRCodeService()

    print("--- Generating QR Code ---")
    # Path resolution
    node = service.api.node("generate_base64")
    
    try:
        b64_result = node(data="https://genropy.org", box_size=5)
        print(f"Success! Base64 length: {len(b64_result)}")
        print(f"Preview (first 40 chars): {b64_result[:40]}...")
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Automatic Validation ---")
    try:
        # box_size must be an integer
        service.api.node("generate_base64")(data="test", box_size="extra-large")
    except Exception as e:
        print(f"Caught validation error: {e}")
