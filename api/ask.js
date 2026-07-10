export default async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { question } = req.body;

    if (!question) {
      return res.status(400).json({ error: 'الرجاء كتابة سؤال' });
    }

    // Temporary response
    res.status(200).json({
      original_question: question,
      fiqh_question: question,
      opinions: [
        {
          title: "اختبار Node.js",
          text: "الـ API شغال الآن بـ Node.js. سنضيف Gemini لاحقاً.",
          source: "نظام الفتاوى",
          link: "",
          type: "text"
        }
      ],
      summary: "النظام يعمل. جاري إضافة الذكاء الاصطناعي.",
      hadiths: []
    });

  } catch (error) {
    res.status(500).json({ error: error.message });
  }
}