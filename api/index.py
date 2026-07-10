import json

def handler(request):
    """Simple Vercel Handler"""
    if request.method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        }

    # Temporary response to test if the route works
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "status": "ok",
            "message": "API is working! GEMINI_KEY is configured.",
            "opinions": [],
            "summary": "الـ API شغال الآن. حطينا handler بسيط للاختبار."
        })
    }
