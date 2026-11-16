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

/** user_written: the sidebar text was typed or edited by the user (`userEdited`), or the
 *  answer exists only in Upwork's own box (typed there). AI-written sidebar text is context
 *  only on the server, never evidence. */
export function otherAnswers(
  questions: { question: string }[],
  index: number,
  sidebarAnswers: Record<string, string>,
  pageValues: string[],
  userEdited: Record<string, boolean> = {},
): { question: string; answer: string; user_written: boolean }[] {
  return questions.flatMap((q, i) => {
    if (i === index) return [];
    const sidebar = (sidebarAnswers[`q${i}`] || '').trim();
    const answer = sidebar || (pageValues[i] || '').trim();
    if (!answer) return [];
    return [{ question: q.question, answer: answer.slice(0, 4000), user_written: sidebar ? !!userEdited[`q${i}`] : true }];
  }).slice(0, 10);
}

/** The answer to revise: the sidebar's text, else what is typed in Upwork's box for it. */
export function currentAnswer(index: number, sidebarAnswers: Record<string, string>, pageValues: string[]): string {
  return (sidebarAnswers[`q${index}`] || pageValues[index] || '').trim().slice(0, 4000);
}
