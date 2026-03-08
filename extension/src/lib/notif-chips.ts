/**
 * Notification chip detection — shared between content script and service worker.
 * Extracted so the content script can compute chips without a SW round trip.
 */

/** For a "$min–$max" range string, return only the upper bound. */
export function topOfRange(amount: string): string {
  const m = amount.match(/\$[\d,]+(?:\.\d+)?\s*[-–]\s*(\$[\d,]+(?:\.\d+)?)/);
  return m ? m[1] : amount;
}

export function extractBudgetFromPageText(
  text: string,
): { amount: string; type: 'hourly' | 'fixed' } | null {
  const labeledHourly = text.match(
    /hourly[:\s\n]+(\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?)/i,
  );
  if (labeledHourly) {
    return { amount: labeledHourly[1].replace(/\s+/g, ''), type: 'hourly' };
  }

  const inlineHourly = text.match(
    /\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?\s*\/\s*h(?:r|our)/i,
  );
  if (inlineHourly) {
    return { amount: inlineHourly[0].replace(/\s+/g, ''), type: 'hourly' };
  }

  const labeledFixed = text.match(
    /(?:fixed[- ]price|est\.?\s*budget|budget|project budget)[:\s\n]+(\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?)/i,
  );
  if (labeledFixed) {
    return { amount: labeledFixed[1].replace(/\s+/g, ''), type: 'fixed' };
  }

  const amtMatch = text.match(/\$([1-9][\d,]{2,})(?:\.\d+)?/);
  if (amtMatch) {
    const num = parseInt(amtMatch[1].replace(/,/g, ''), 10);
    if (num >= 100) {
      return { amount: amtMatch[0].replace(/\s+/g, ''), type: 'fixed' };
    }
  }

  return null;
}

export function detectNotifChips(
  title: string,
  description: string,
  budgetAmount: string | null,
  budgetType: string | null,
): string[] {
  const text = `${title} ${description}`;
  const lower = text.toLowerCase();
  const chips: string[] = [];

  if (/\bmvp\b|minimum viable product/i.test(text))                              chips.push('MVP');
  if (/\bsaas\b|software.as.a.service/i.test(text))                              chips.push('SaaS');
  if (/\bazure\b/i.test(text))                                                    chips.push('Azure');
  if (/\bsql\b|postgresql|mysql|sql\s*server|sqlite|nosql|mongodb/i.test(text))  chips.push('SQL');
  if (/\b(ai|llm|gpt|openai|claude|anthropic|rag|vector|chatbot|langchain|embedding|fine.?tun)/i.test(text)) chips.push('AI');
  if (/\bpython\b/i.test(text))                                                   chips.push('Python');
  if (/\breact\b/i.test(text))                                                    chips.push('React');
  if (/\b(api|rest|fastapi|graphql|webhook|endpoint)\b/i.test(text))             chips.push('API');
  if (/\b(fractional\s+cto|cto|technical\s+(co-?founder|advisor|lead)|vp\s+of\s+eng)/i.test(text)) chips.push('CTO');
  if (/\b(aws|gcp|google cloud|cloud|terraform|kubernetes|k8s|docker|devops|infra)/i.test(text)) chips.push('Cloud');
  if (/\b(n8n|zapier|make\.com|make\b|integromat|automation|workflow\s+automat)/i.test(text)) chips.push('Auto');
  if (/\b(asap|urgent|immediately|right away|start today|start now|quick turnaround)/i.test(lower)) chips.push('Urgent');
  if (/\b(long.?term|ongoing|retainer|6\s*month|12\s*month|part.?time|full.?time|staff aug)/i.test(lower)) chips.push('Long-term');
  if (!chips.includes('Long-term') && /\b(role|position|ongoing|retainer|staff)\b/.test(lower)) chips.push('Role');

  if (budgetAmount) {
    const clean = topOfRange(budgetAmount.trim());
    if (budgetType === 'hourly') {
      chips.push(clean.includes('/hr') || clean.includes('/hour') ? clean : `${clean}/hr`);
    } else {
      chips.push(clean);
    }
  } else {
    const extracted = extractBudgetFromPageText(text);
    if (extracted) {
      const top = topOfRange(extracted.amount);
      const label = extracted.type === 'hourly'
        ? (top.includes('/hr') ? top : `${top}/hr`)
        : top;
      chips.push(label);
    }
  }

  return chips;
}
