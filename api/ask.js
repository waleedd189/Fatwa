    // Gemini API Call
    const geminiResponse = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{
          parts: [{
            text: `السؤال: ${question}\n\nأجب بفتوى إسلامية موجزة وواضحة مع خلاصة عملية.`
          }]
        }]
      })
    });

    const data = await geminiResponse.json();
    
    if (!geminiResponse.ok) {
      console.error("Gemini Error:", data);
      throw new Error("Gemini API error");
    }

    const answer = data.candidates?.[0]?.content?.parts?.[0]?.text || "لا توجد إجابة حالياً.";
