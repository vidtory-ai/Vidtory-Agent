# Agent Designer Onboarding UX Flow

## 1. Product Intent

This onboarding flow is designed for an enterprise **Agent Designer** that helps customers create brand-consistent visual assets with AI.

The core user segments are:

- **Brand Marketing**: teams creating campaign visuals, brand content, mascot content, social assets, banners, and branded ad creatives.
- **Fashion Studio**: teams creating fashion product images, lookbook visuals, model/editorial concepts, product styling directions, and collection launch assets.

The goal is to keep onboarding extremely simple while still collecting enough structured information for the AI agent to produce high-quality design output.

The onboarding should feel less like filling out a form and more like:

> "Upload a few signals. The AI understands my brand. I confirm the direction. Then it starts designing."

---

## 2. Experience Principle

The flow should follow a retention-first structure inspired by the MrBeast formula:

| Retention Principle | UX Translation |
|---|---|
| Big Promise | Tell the user they will get a usable design direction quickly |
| Simple Rules | Keep each screen to one decision |
| Fast Payoff | Show AI interpretation immediately after each input |
| Escalation | Move from goal -> brand understanding -> style -> first design |
| Micro-hooks | End each step with a reason to continue |
| Emotional Payoff | User feels the agent understands their brand with minimal effort |

The user should never feel:

> "I am setting up a database."

They should feel:

> "I am teaching an AI designer my brand in under 3 minutes."

---

## 3. Recommended High-Level Flow

Keep onboarding to **5 main steps**:

1. **Choose Design Goal**
2. **Select Business Context**
3. **Upload Brand Signals**
4. **Confirm AI Brand Snapshot**
5. **Choose Design Direction and Start**

Optional advanced inputs should be progressively revealed after the first design, not forced before it.

---

## 4. Step 1: Choose Design Goal

### UX Goal

Start with the user's desired output, not with company information.

This creates immediate relevance and allows the system to ask fewer questions later.

### Screen Title

**What do you want your AI designer to create first?**

### Subtitle

**Choose one starting goal. The agent will tailor the setup around this output.**

### Options

For all users:

- Social media post
- Product ad creative
- Campaign key visual
- Website / ecommerce banner
- Product image concept
- Lookbook / editorial image
- Mascot or brand character content
- Other

### Recommended Interaction

Use large visual cards, not a dropdown.

Each card should show:

- asset type name
- small preview thumbnail
- short use case

Example:

**Product Ad Creative**  
For ecommerce, paid ads, launches, and offer-led visuals.

### AI Behavior

After user selection, the AI should immediately infer what information is needed next.

Example:

> "Great. For product ad creative, I will prioritize product clarity, brand colors, visual hierarchy, and conversion-focused layout."

### Mini-Hook

> "Next, I will identify whether this should behave like a Brand Marketing agent or a Fashion Studio agent."

### DB Fields

```json
{
  "onboarding_goal": {
    "asset_type": "product_ad_creative",
    "first_output_goal": "conversion_asset",
    "selected_at": "timestamp"
  }
}
```

---

## 5. Step 2: Select Business Context

### UX Goal

Separate **Brand Marketing** and **Fashion Studio** early because they have different quality criteria.

Brand Marketing cares about campaign fit, brand recognition, voice, and consistency.

Fashion Studio cares about product fidelity, styling clarity, model/look direction, texture, silhouette, and visual precision.

### Screen Title

**Which team is this agent designing for?**

### Subtitle

**This helps the agent judge what "good design" means for your workflow.**

### Primary Options

#### Option A: Brand Marketing

Use this if you create:

- campaign visuals
- branded social posts
- mascot content
- ad concepts
- launch banners
- brand storytelling assets

Quality standard:

> On-brand, recognizable, campaign-ready, emotionally clear.

#### Option B: Fashion Studio

Use this if you create:

- product images
- fashion editorials
- collection visuals
- lookbook concepts
- model styling references
- ecommerce fashion assets

Quality standard:

> Product-accurate, style-consistent, visually polished, production-ready.

#### Option C: Both

Use this if the customer needs brand-led fashion or campaign-led product imagery.

Quality standard:

> Brand-consistent and product-accurate.

### Optional Quick Filter

After selecting the segment, ask only one follow-up:

**What matters most for this first design?**

For Brand Marketing:

- Strong brand recognition
- Campaign storytelling
- Social engagement
- Premium brand feel
- Conversion / ad performance

For Fashion Studio:

- Product accuracy
- Styling direction
- Editorial mood
- Model / pose direction
- Ecommerce-ready clarity

### AI Behavior

The AI should adapt the rest of onboarding based on this selection.

Example for Brand Marketing:

> "I will prioritize brand consistency, campaign fit, layout clarity, and repeatable visual rules."

Example for Fashion Studio:

> "I will prioritize product fidelity, styling details, material accuracy, silhouette, and clean visual presentation."

### Mini-Hook

> "Now upload one brand signal. I will extract the first version of your design rules automatically."

### DB Fields

```json
{
  "business_context": {
    "segment": "brand_marketing",
    "priority": "strong_brand_recognition",
    "quality_standard": [
      "brand_consistency",
      "campaign_fit",
      "visual_recognition"
    ]
  }
}
```

---

## 6. Step 3: Upload Brand Signals

### UX Goal

Reduce manual work by letting AI infer brand guidelines from existing assets.

Instead of asking the customer to type colors, fonts, style, and tone manually, ask for one or more source signals.

### Screen Title

**Add one brand signal**

### Subtitle

**Upload a logo or paste a website. The AI will create a draft brand snapshot for you to confirm.**

### Input Options

Recommended order:

1. Upload logo
2. Paste website URL
3. Upload product image
4. Upload brand guideline PDF
5. Upload reference image
6. Paste short brand description

### UX Rule

Do not require all inputs.

Minimum viable onboarding should work with only:

- one logo, or
- one website URL, or
- one product image

### AI Extraction

From logo:

- primary color
- secondary colors
- accent colors
- neutral colors
- logo type
- typography style guess
- visual mood
- contrast level
- likely design styles

From website:

- brand positioning
- color palette
- typography cues
- visual density
- product category
- tone of voice
- design maturity
- CTA style

From product image:

- product category
- material / texture cues
- dominant colors
- product shape and silhouette
- suitable visual treatments
- background compatibility

From brand guideline:

- official color palette
- logo usage rules
- typography rules
- tone of voice
- visual dos and don'ts
- compliance restrictions

### Loading Experience

Do not show a generic spinner.

Show progressive AI discoveries:

- "Extracting colors..."
- "Detecting visual mood..."
- "Checking logo style..."
- "Finding suitable design directions..."
- "Drafting brand rules..."

### Mini-Wow

Show a quick result within seconds:

> "I found 5 brand colors and 3 likely design directions."

### Mini-Hook

> "Next, confirm the AI's read of your brand so the first design starts closer to your taste."

### DB Fields

```json
{
  "brand_sources": {
    "logo_url": "string",
    "website_url": "string",
    "product_image_urls": [],
    "brand_guideline_url": "string",
    "reference_image_urls": []
  },
  "ai_extracted_brand": {
    "colors": {
      "primary": "hex",
      "secondary": ["hex"],
      "accent": ["hex"],
      "neutral": ["hex"]
    },
    "logo_type": "wordmark",
    "logo_style": ["minimal", "premium"],
    "typography_guess": "modern_sans",
    "brand_mood": ["clean", "confident", "premium"],
    "contrast_level": "medium",
    "visual_density": "low"
  }
}
```

---

## 7. Step 4: Confirm AI Brand Snapshot

### UX Goal

Let AI do the heavy lifting, then ask the customer to confirm or lightly correct.

This is the most important "wow" moment in onboarding.

### Screen Title

**Here is how the AI understands your brand**

### Subtitle

**Confirm what looks right. You can adjust anything later.**

### Snapshot Layout

Show a compact brand card:

#### Brand Mood

Example:

- Clean
- Premium
- Confident

#### Color Direction

Example:

- Primary: Black
- Secondary: White
- Accent: Gold

#### Layout Direction

Example:

- Low text density
- Strong product focus
- Large negative space
- Clear hero object

#### Image Direction

Example:

- Studio lighting
- Soft shadow
- High product clarity
- Minimal background

#### Avoid

Example:

- Neon colors
- Busy collage
- Childish graphics
- Unapproved claims

### Confirmation Controls

Avoid asking users to edit many fields manually.

Use quick buttons:

- Looks right
- More premium
- More playful
- More bold
- Softer / more elegant
- More editorial
- More product-focused
- Change colors
- Change style

### Segment-Specific Snapshot

#### If Brand Marketing

Add:

- campaign fit
- brand voice
- mascot usage if detected
- social/ad suitability
- recognition cues

Example AI summary:

> "Your brand appears clean, confident, and premium. I will keep layouts simple, use strong visual hierarchy, and avoid noisy campaign treatments."

#### If Fashion Studio

Add:

- product fidelity
- fabric / texture emphasis
- model styling direction
- editorial vs ecommerce balance
- silhouette visibility

Example AI summary:

> "Your visual direction appears editorial and polished. I will protect garment shape, material texture, styling clarity, and collection consistency."

### Mini-Wow

After confirmation, show:

> "Brand snapshot saved. The agent now has enough context to generate your first design direction."

### Mini-Hook

> "Before designing, choose the style lane you want the agent to start from."

### DB Fields

```json
{
  "confirmed_brand_profile": {
    "brand_mood": ["clean", "premium", "confident"],
    "confirmed_colors": {
      "primary": "hex",
      "secondary": ["hex"],
      "accent": ["hex"]
    },
    "layout_rules": [
      "low_text_density",
      "large_product_focus",
      "clear_visual_hierarchy"
    ],
    "image_rules": [
      "studio_lighting",
      "minimal_background",
      "soft_shadow"
    ],
    "avoid_rules": [
      "neon_colors",
      "busy_layout",
      "unapproved_claims"
    ],
    "confirmation_status": "user_confirmed"
  }
}
```

---

## 8. Step 5: Choose Design Direction

### UX Goal

Give users a small number of familiar design style options.

The user should not need to understand design vocabulary deeply. Each style should be explained through use case and feeling.

### Screen Title

**Choose a starting design style**

### Subtitle

**The AI recommends these based on your brand. Pick one main style.**

### Recommended Style Options

#### 1. Clean Premium

Best for:

- premium ecommerce
- beauty
- lifestyle
- minimal brand campaigns

Feels:

- clean
- expensive
- calm
- polished

Avoids:

- clutter
- loud colors
- excessive copy

#### 2. Bold Performance

Best for:

- paid ads
- ecommerce campaigns
- sale launches
- attention-grabbing social assets

Feels:

- direct
- energetic
- clear
- conversion-focused

Avoids:

- vague storytelling
- overly subtle hierarchy
- weak CTA

#### 3. Editorial Fashion

Best for:

- fashion campaigns
- lookbooks
- collection launches
- model-led imagery

Feels:

- stylish
- curated
- magazine-like
- art-directed

Avoids:

- overly salesy design
- generic ecommerce layouts
- heavy text

#### 4. Product Hero

Best for:

- product images
- ecommerce hero banners
- product launch visuals
- catalog assets

Feels:

- clear
- focused
- commercial
- product-first

Avoids:

- distracting backgrounds
- unclear product shape
- cropped product details

#### 5. Playful Brand Character

Best for:

- mascot content
- social engagement
- youth brands
- friendly campaign concepts

Feels:

- fun
- memorable
- expressive
- accessible

Avoids:

- corporate stiffness
- overly minimal storytelling
- generic stock-like visuals

#### 6. Natural Organic

Best for:

- wellness
- skincare
- food
- eco products
- soft lifestyle brands

Feels:

- warm
- natural
- trustworthy
- gentle

Avoids:

- harsh contrast
- synthetic visual effects
- aggressive ad language

### Segment-Specific Recommendation Logic

#### Brand Marketing

Recommended default styles:

- Clean Premium
- Bold Performance
- Playful Brand Character
- Natural Organic

Useful when the goal is brand recognition, campaign expression, social engagement, or ad performance.

#### Fashion Studio

Recommended default styles:

- Editorial Fashion
- Product Hero
- Clean Premium
- Natural Organic

Useful when the goal is styling clarity, garment fidelity, collection consistency, or premium editorial output.

### AI Behavior

The system should pre-select or rank styles based on AI-extracted brand signals.

Example:

> "Recommended: Clean Premium. Your logo uses a minimal wordmark and high-contrast palette, so this is likely the safest starting point."

### Mini-Wow

After selection:

> "Great. I will start with Clean Premium, but keep the product large and campaign-ready for your first output."

### Mini-Hook

> "Now I will generate 3 first directions: safe, performance, and creative stretch."

### DB Fields

```json
{
  "design_style_preferences": {
    "primary_style": "clean_premium",
    "secondary_styles": ["product_hero"],
    "ai_recommended_styles": [
      {
        "style": "clean_premium",
        "confidence": 0.86,
        "reason": "minimal logo and premium color palette"
      }
    ],
    "user_selected_style": "clean_premium"
  }
}
```

---

## 9. First Design Generation

### UX Goal

Do not end onboarding with a confirmation screen.

End it with a first tangible output.

The user should see the agent immediately move from setup to creation.

### Screen Title

**Your first design directions are ready**

### Output Structure

Generate 3 directions:

#### Option A: Safe Brand Fit

Purpose:

- closest to detected brand guideline
- low risk
- best for first approval

Show:

- design preview
- color usage
- layout logic
- why it fits the brand

#### Option B: Performance Version

Purpose:

- stronger hierarchy
- clearer offer or message
- better for paid/social testing

Show:

- design preview
- hook/copy direction
- CTA treatment
- risk level

#### Option C: Creative Stretch

Purpose:

- more expressive
- useful for campaign exploration
- still inside guardrails

Show:

- design preview
- creative idea
- where it can be used
- what may need approval

### Feedback Buttons

Under each option:

- More like this
- Make more premium
- Make more bold
- Reduce text
- Increase product focus
- Change colors
- Save as default style

### Mini-Wow

After user selects a direction:

> "I will remember this choice. Future designs will start closer to this style."

### Mini-Hook

> "After 3 selections, I can create a reusable brand design playbook for your team."

### DB Fields

```json
{
  "first_design_session": {
    "generated_options": [
      "safe_brand_fit",
      "performance_version",
      "creative_stretch"
    ],
    "selected_direction": "safe_brand_fit",
    "feedback_actions": ["make_more_premium", "reduce_text"],
    "style_learning_signal": {
      "prefers_low_text_density": true,
      "prefers_premium_layout": true,
      "prefers_product_focus": true
    }
  }
}
```

---

## 10. Simplified End-to-End Flow

The final flow should feel like this:

```text
1. What do you want to create?
2. Is this for Brand Marketing or Fashion Studio?
3. Upload logo, website, product image, or brand guide.
4. AI creates brand snapshot.
5. User confirms or lightly adjusts.
6. User selects one recommended design style.
7. AI generates 3 first design directions.
8. User selects the closest one.
9. Agent saves learning signal for future work.
```

Target onboarding time:

- **Fast path:** 60-90 seconds
- **Normal path:** 2-4 minutes
- **Advanced path:** 5-8 minutes

---

## 11. Copywriting Examples

### Opening Copy

> "Create your first on-brand design direction in minutes. Start with a logo, website, or product image. The AI will build the first version of your brand design rules automatically."

### After Goal Selection

> "Got it. I will optimize the setup for campaign-ready brand visuals."

or

> "Got it. I will optimize the setup for product-accurate fashion visuals."

### After Upload

> "I found your core colors, visual mood, and likely design style."

### Brand Snapshot CTA

> "Looks right"

> "Make it more premium"

> "Make it more playful"

> "Change style"

### Before First Design

> "Your AI designer now has a brand snapshot, style direction, and safety rules. Let's create the first design."

### After First Design

> "Choose the direction closest to your brand. The agent will learn from this choice."

---

## 12. Mini-Hook System

Mini-hooks should appear at the end of each step to create momentum.

| Step | Mini-Hook |
|---|---|
| After design goal | "Next, I will adapt the agent for your type of team." |
| After segment selection | "Now I only need one brand signal to create a draft guideline." |
| After upload | "I found your colors and visual mood. Confirm the brand snapshot next." |
| After brand snapshot | "Choose the style lane so the first design starts closer to your taste." |
| After style selection | "I will generate 3 directions: safe, performance, and creative stretch." |
| After first design | "Pick the closest one. The agent will remember this for next time." |
| After 3 feedback actions | "Your design preferences are becoming consistent enough to save as a team playbook." |

---

## 13. What To Avoid

Avoid asking too many manual questions upfront:

- "What are your brand colors?"
- "What fonts do you use?"
- "Describe your design style."
- "What layout do you prefer?"
- "What should the agent avoid?"

Instead, let AI infer first, then ask for confirmation:

- "I found these colors. Keep them?"
- "This looks like a Clean Premium brand. Is that right?"
- "I suggest avoiding neon colors and crowded layouts. Confirm?"
- "This style seems closest to your logo. Start here?"

Avoid ending onboarding with:

> "Setup complete."

End with:

> "Here are your first 3 design directions."

---

## 14. Recommended Database Model

Separate raw AI inference from user-confirmed brand rules.

```json
{
  "workspace_id": "string",
  "brand_id": "string",
  "onboarding_goal": {
    "asset_type": "string",
    "first_output_goal": "string"
  },
  "business_context": {
    "segment": "brand_marketing | fashion_studio | both",
    "priority": "string",
    "quality_standard": []
  },
  "brand_sources": {
    "logo_url": "string",
    "website_url": "string",
    "product_image_urls": [],
    "brand_guideline_url": "string",
    "reference_image_urls": []
  },
  "ai_extracted_brand": {
    "colors": {},
    "logo_type": "string",
    "logo_style": [],
    "brand_mood": [],
    "typography_guess": "string",
    "contrast_level": "string",
    "visual_density": "string",
    "confidence_score": 0.0
  },
  "confirmed_brand_profile": {
    "colors": {},
    "brand_mood": [],
    "layout_rules": [],
    "image_rules": [],
    "avoid_rules": [],
    "confirmation_status": "ai_inferred | user_confirmed | user_modified"
  },
  "design_style_preferences": {
    "primary_style": "string",
    "secondary_styles": [],
    "ai_recommended_styles": [],
    "user_selected_style": "string"
  },
  "learning_signals": {
    "selected_directions": [],
    "rejected_directions": [],
    "feedback_actions": [],
    "winning_patterns": [],
    "last_updated": "timestamp"
  }
}
```

Key rule:

> Never overwrite confirmed brand data with new AI inference. Store new inference as a suggestion until the user confirms it.

---

## 15. Progressive Disclosure After Onboarding

Do not ask everything before the first design.

Ask deeper questions only when needed:

### After First Design

Ask:

> "Which direction is closest to your brand?"

Save:

- selected direction
- rejected directions
- feedback action

### After 3 Designs

Ask:

> "I noticed you prefer premium layouts with low text density. Save this as your default?"

Save:

- recurring style pattern
- team-level default

### Before Publishing

Ask:

> "Should this type of output require approval before export?"

Save:

- approval rules
- compliance triggers

### When User Uploads More Assets

Ask:

> "This new reference changes the style direction slightly. Should I update the brand profile?"

Save:

- suggested update
- confirmed update
- rejected update

---

## 16. Final Recommended UX

The best version of this onboarding is:

> Goal first, segment second, AI inference third, user confirmation fourth, design output fifth.

The customer should only make a few easy choices:

1. What do you want to create?
2. Is this for Brand Marketing or Fashion Studio?
3. Upload one brand signal.
4. Confirm the AI's read.
5. Pick one design style.

Everything else should be inferred, suggested, or learned over time.

This keeps the experience simple while still giving the AI enough structured data to produce high-quality output.

The biggest wow moment is not the form.

The biggest wow moment is when the customer sees:

> "From one logo, the agent already understands my colors, style, mood, design direction, and what to avoid."

That is the moment onboarding becomes product magic instead of setup work.
