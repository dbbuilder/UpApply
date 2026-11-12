/** Context for one screening answer (Apply panel): the other questions' answers, so answers build
 *  on each other and never repeat. The sidebar's text wins; otherwise what is already typed in
 *  Upwork's own box (answers Chris wrote there himself) counts too. */
export type AnswerTweak = 'shorter' | 'specific' | 'link' | 'number';

export const TWEAK_LABELS: Record<AnswerTweak, string> = {
  shorter: 'Shorter',
  specific: 'More specific',
  link: 'Add a link',
  number: 'Add a number',
};

export function otherAnswers(
  questions: { question: string }[],
  index: number,
  sidebarAnswers: Record<string, string>,
  pageValues: string[],
): { question: string; answer: string }[] {
  return questions.flatMap((q, i) => {
    if (i === index) return [];
    const answer = (sidebarAnswers[`q${i}`] || pageValues[i] || '').trim();
    return answer ? [{ question: q.question, answer: answer.slice(0, 4000) }] : [];
  }).slice(0, 10);
}

/** The answer to revise: the sidebar's text, else what is typed in Upwork's box for it. */
export function currentAnswer(index: number, sidebarAnswers: Record<string, string>, pageValues: string[]): string {
  return (sidebarAnswers[`q${index}`] || pageValues[index] || '').trim().slice(0, 4000);
}
