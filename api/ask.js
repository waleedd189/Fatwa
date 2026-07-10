export default async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    return res.status(200).end();
  }

  try {
    const { question } = req.body;

    if (!question) {
      return res.status(400).json({ error: 'الرجاء كتابة سؤال' });
    }

    const GEMINI_KEY = process.env.GEMINI_KEY;
    if (!GEMINI_KEY) {
      return res.status(500).json({ error: 'GEMINI_KEY غير معرف' });
    }

    // Gemini API Call
    const geminiResponse = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: `أجب على السؤال الديني ده بفتوى موجزة وخلاصة: ${question}` }] }]
      })
    });

    const data = await geminiResponse.json();
    const answer = data.candidates?.[0]?.content?.parts?.[0]?.text || "لم أتمكن من الحصول على إجابة.";

    res.status(200).json({
      original_question: question,
      fiqh_question: question,
      opinions: [{
        title: "فتوى من Gemini",
        text: answer,
        source: "Google Gemini",
        link: "",
        type: "text"
      }],
      summary: answer.substring(0, 150) + "...",
      hadiths: []
    });

  } catch (error) {
    console.error(error);
    res.status(500).json({ error: "حدث خطأ أثناء معالجة السؤال" });
  }
}
