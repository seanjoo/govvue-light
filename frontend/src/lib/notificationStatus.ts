export function emailStatusLabel(status: string) {
  return status === 'SKIPPED' ? 'Not sent — no matches' : status;
}
