"""Brief topics: retrieval queries + metric hints per backlog item (PLAN.md §5)."""

TOPICS = {
    "how-the-company-makes-money": {
        "title": "How the company makes money",
        "entities": ["cof"],
        "queries": [
            "net interest income credit card yield funding costs",
            "interchange fee income non-interest income composition",
            "deposit funding franchise cost of deposits",
            "provision for credit losses allowance methodology",
            "credit card segment profitability revenue margin",
        ],
        "metric_hints": ["net interest income", "noninterest income", "net income",
                         "credit card loans", "deposits"],
    },
    "discover-acquisition": {
        "title": "The Discover acquisition",
        "entities": ["cof", "dfs"],
        "queries": [
            "Discover merger rationale strategic network",
            "merger agreement terms exchange ratio",
            "background of the merger negotiations",
            "Discover network payments vertical integration",
            "merger integration regulatory approval conditions",
        ],
        "metric_hints": [],
    },
    "corporate-history": {
        "title": "Corporate history and lineage",
        "entities": ["cof"],
        "queries": [
            "Signet spinoff initial public offering history",
            "acquisitions Hibernia North Fork ING Direct HSBC card",
            "business evolution monoline diversified bank",
        ],
        "metric_hints": ["total assets"],
    },
    "credit-cycle-posture": {
        "title": "Credit cycle posture",
        "entities": ["cof"],
        "queries": [
            "underwriting discipline credit normalization cycle",
            "charge-off delinquency trends outlook",
            "allowance build release credit outlook CECL",
        ],
        "metric_hints": ["charge-offs", "delinquency", "allowance", "provision"],
    },
    "technology-thesis": {
        "title": "The technology thesis",
        "entities": ["cof"],
        "queries": [
            "cloud migration public cloud AWS data centers exit",
            "technology transformation software engineers modern stack",
            "machine learning artificial intelligence customer experience",
        ],
        "metric_hints": [],
    },
    "deposit-strategy": {
        "title": "Deposit strategy",
        "entities": ["cof", "cona"],
        "queries": [
            "digital bank national direct deposits branch-light cafes",
            "deposit growth retail funding insured deposits",
        ],
        "metric_hints": ["deposits", "sod"],
    },
    "segment-map": {
        "title": "Segment map",
        "entities": ["cof"],
        "queries": [
            "credit card segment results income loans",
            "consumer banking segment auto deposits results",
            "commercial banking segment results",
        ],
        "metric_hints": ["net income", "loans"],
    },
    "regulatory-posture": {
        "title": "Regulatory posture",
        "entities": ["cof"],
        "queries": [
            "consent order enforcement compliance remediation",
            "capital requirements stress capital buffer CET1 requirement",
            "supervisory matters regulatory risk",
        ],
        "metric_hints": ["cet1"],
    },
    "partnership-history": {
        "title": "Partnership history",
        "entities": ["cof"],
        "queries": [
            "co-brand partnership card agreement Walmart Costco retail",
            "partnership termination portfolio sale acquisition card",
        ],
        "metric_hints": [],
    },
    "competitive-field": {
        "title": "Competitive field",
        "entities": ["cof", "dfs"],
        "queries": [
            "competition credit card issuers networks Visa Mastercard American Express",
            "competitive landscape banking market share",
        ],
        "metric_hints": [],
    },
    "data-breach-2019": {
        "title": "The 2019 data breach and aftermath",
        "entities": ["cof"],
        "queries": [
            "2019 data breach cybersecurity incident unauthorized access",
            "breach settlement consent order penalties remediation",
        ],
        "metric_hints": [],
    },
    "marketing-brand-strategy": {
        "title": "Marketing and brand strategy",
        "entities": ["cof"],
        "queries": [
            "marketing spend brand advertising strategy",
            "customer acquisition national brand campaigns",
        ],
        "metric_hints": ["marketing expense"],
    },
}
