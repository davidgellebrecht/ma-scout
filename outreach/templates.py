"""
outreach/templates.py — LLM-Generated Outreach

Uses Claude to generate personalized acquisition outreach letters and
emails based on which signals fired for a given company.  The idea is
to craft a message that speaks to the owner's likely situation without
revealing the scoring methodology.

Three template types:
    1. acquisition_letter — Formal letter: "Have you thought about your exit plan?"
    2. intro_email — Casual email: introduce the buyer, suggest a coffee meeting
    3. partnership_inquiry — "We'd like to help with overflow work" (foot-in-door)

The LLM prompt includes the company's details and fired signals, then
asks for a warm, non-aggressive message appropriate to the owner's
likely mindset.
"""

import config
from models import CompanyWithSignals


# ── Signal-to-messaging map ──────────────────────────────────────────────────
# Maps each signal to the tone and angle that resonates best with that
# particular type of acquisition target.

SIGNAL_MESSAGING = {
    "cslb_lifecycle": {
        "angle": "retirement and succession planning",
        "tone": "respectful, acknowledging their decades of hard work",
        "context": (
            "The owner has been running this business for {years} years "
            "as a sole proprietor.  They may be thinking about retirement "
            "but unsure how to exit gracefully."
        ),
    },
    "digital_ghost": {
        "angle": "legacy preservation",
        "tone": "appreciative of their reputation, not critical of inactivity",
        "context": (
            "The company has a strong reputation ({rating}★) but hasn't "
            "been actively managing their online presence.  The owner may "
            "be coasting or burnt out."
        ),
    },
    "permit_pipeline": {
        "angle": "partnership and capacity support",
        "tone": "helpful, offering to solve an immediate problem",
        "context": (
            "The company has taken on large projects (${value:,.0f} in "
            "active permits) that may be stretching their small crew.  "
            "They likely need help NOW."
        ),
    },
    "fleet_aging": {
        "angle": "equipment investment and business modernization",
        "tone": "empathetic about the cost of staying competitive",
        "context": (
            "The company's equipment shows signs of aging.  The owner "
            "faces a tough choice: invest $100K+ in new trucks or find "
            "another path forward."
        ),
    },
}


def generate_outreach(
    target: CompanyWithSignals,
    template_type: str = "intro_email",
    buyer_name: str = "a local landscape management group",
) -> str:
    """
    Generate a personalized outreach message using Claude.

    Parameters
    ----------
    target : CompanyWithSignals
        The company to generate outreach for.
    template_type : str
        One of: "acquisition_letter", "intro_email", "partnership_inquiry"
    buyer_name : str
        How to describe the buyer in the message.

    Returns
    -------
    str — The generated message text.
    """
    if not config.ANTHROPIC_API_KEY:
        return _fallback_template(target, template_type, buyer_name)

    try:
        import anthropic
    except ImportError:
        return _fallback_template(target, template_type, buyer_name)

    # Build the prompt
    company = target.company
    fired_signals = [s for s in target.signals if s.signal]

    # Gather context from fired signals
    signal_contexts = []
    for signal in fired_signals:
        messaging = SIGNAL_MESSAGING.get(signal.layer_name, {})
        context_template = messaging.get("context", "")
        # Fill in template variables from signal data
        try:
            context = context_template.format(
                years=signal.data.get("years_active", "many"),
                rating=signal.data.get("best_rating", "high"),
                value=signal.data.get("total_permit_value", 0),
            )
        except (KeyError, ValueError):
            context = context_template
        signal_contexts.append(context)

    angles = [
        SIGNAL_MESSAGING.get(s.layer_name, {}).get("angle", "")
        for s in fired_signals
    ]
    tones = [
        SIGNAL_MESSAGING.get(s.layer_name, {}).get("tone", "")
        for s in fired_signals
    ]

    type_instructions = {
        "acquisition_letter": (
            "Write a formal business letter (with date and addresses) "
            "suggesting the owner consider their exit plan and offering "
            "to acquire the business.  Tone: professional, respectful, "
            "not pushy."
        ),
        "intro_email": (
            "Write a brief, warm email introducing the buyer and "
            "suggesting a casual meeting (coffee, lunch).  Tone: "
            "conversational, genuine interest, no pressure."
        ),
        "partnership_inquiry": (
            "Write an email offering to partner on overflow work or "
            "subcontract.  This is a foot-in-the-door approach — the "
            "goal is to build a relationship that could lead to an "
            "acquisition later.  Tone: helpful, collaborative."
        ),
    }

    prompt = f"""Generate a personalized outreach message for a landscaping business acquisition opportunity.

TARGET COMPANY:
- Business name: {company.business_name}
- Owner name: {company.owner_name or 'Owner'}
- City: {company.city or 'Orange County'}
- Years in business: {fired_signals[0].data.get('years_active', 'many') if fired_signals else 'many'}

BUYER: {buyer_name}

MESSAGE TYPE: {type_instructions.get(template_type, type_instructions['intro_email'])}

CONTEXT (why this company was identified — DO NOT mention scoring or data analysis):
{chr(10).join(f'- {c}' for c in signal_contexts if c)}

MESSAGING ANGLES TO WEAVE IN: {', '.join(a for a in angles if a)}
TONE GUIDANCE: {', '.join(t for t in tones if t)}

IMPORTANT RULES:
- Never mention that the owner was identified by an algorithm or data analysis
- Never mention specific scores, signals, or screening criteria
- Sound like a real person, not a form letter
- Keep it under 250 words
- Include a clear but gentle call to action (phone call, coffee meeting, etc.)
"""

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"  ⚠  Outreach generation error: {e}")
        return _fallback_template(target, template_type, buyer_name)


def _fallback_template(
    target: CompanyWithSignals,
    template_type: str,
    buyer_name: str,
) -> str:
    """
    Simple template fallback when the Claude API is unavailable.
    Returns a basic but personalized message.
    """
    company = target.company
    owner = company.owner_name or "Owner"
    name = company.business_name

    if template_type == "acquisition_letter":
        return f"""Dear {owner},

I'm writing to introduce myself. I represent {buyer_name}, and we've been \
impressed by the reputation {name} has built in {company.city or 'Orange County'} \
over the years.

As the landscape industry evolves, many established business owners are \
exploring their options for the future. Whether you're considering \
retirement, looking to reduce your workload, or simply curious about \
what your business is worth, we'd welcome the chance to have a \
confidential conversation.

We're not looking to change what makes {name} successful — we're \
interested in preserving the relationships and quality your clients \
have come to expect.

Would you be open to a brief phone call at your convenience?

Respectfully,
{buyer_name}
"""

    elif template_type == "partnership_inquiry":
        return f"""Hi {owner},

I run {buyer_name} here in OC, and I wanted to reach out about a \
potential partnership opportunity.

We've been expanding our capacity and are looking for experienced \
crews to collaborate with on overflow projects. If you ever find \
yourself stretched thin on a big job, we'd be happy to lend a hand \
as a subcontractor — and vice versa.

No pressure at all. Just thought it might be worth a conversation \
over coffee sometime.

Best,
{buyer_name}
"""

    else:  # intro_email
        return f"""Hi {owner},

Quick note to introduce myself — I'm with {buyer_name}, a local \
landscape management group here in Orange County.

I've heard good things about {name} and the work you do in \
{company.city or 'the area'}. I'd love to buy you a coffee sometime \
and learn more about your business. No agenda, just always looking \
to connect with fellow professionals in the industry.

Would any morning this week or next work for you?

Best,
{buyer_name}
"""
