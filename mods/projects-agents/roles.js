// Labels describe project identity, never inferred from process or task status.
export function projectRole(terminal) {
  return ({main:'PM',worker:'Worker','former-main':'前 PM'})[terminal?.labels?.['projects.role']] || null;
}
export function projectHint(terminal) {
  const role=projectRole(terminal);
  if(!role)return '';
  return [role,terminal.labels['projects.name']||terminal.labels['projects.project'],terminal.address].filter(Boolean).join(' · ');
}
