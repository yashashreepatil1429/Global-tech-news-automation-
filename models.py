CATEGORY_KEYWORDS = {
    "Agentic AI": (
        "agentic ai",
        "ai agent",
        "autonomous agent",
        "agentic",
    ),
    "AI": (
        "artificial intelligence",
        "generative ai",
        "machine learning",
        "large language model",
        "llm",
    ),
    "Quantum Computing": (
        "quantum computing",
        "quantum computer",
        "quantum",
        "qubit",
    ),
    "Cloud": (
        "cloud computing",
        "cloud service",
        "cloud platform",
        "aws",
        "azure",
        "google cloud",
    ),
    "Cybersecurity": (
        "cybersecurity",
        "cyber security",
        "ransomware",
        "data breach",
        "vulnerability",
        "malware",
    ),
    "Programming": (
        "programming",
        "programming language",
        "python",
        "javascript",
        "software development",
        "open source",
    ),
    "Developer Tools": (
        "developer tool",
        "developer platform",
        "ide",
        "code editor",
        "api",
        "software architecture",
    ),
    "Startups": (
        "startup",
        "start-up",
        "venture capital",
        "funding round",
        "ipo",
    ),
    "Technology Companies": (
        "technology company",
        "tech company",
        "apple",
        "google",
        "microsoft",
        "nvidia",
        "meta",
        "amazon",
    ),
}


def categorize_news(title, description=""):
    text = f"{title} {description}".casefold()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return category

    return "Other Technology"
