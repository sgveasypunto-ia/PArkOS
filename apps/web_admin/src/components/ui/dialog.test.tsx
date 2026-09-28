/**
 * `dialog.test.tsx` -- the accessibility contract of the modal primitive.
 *
 * These are behaviour tests, not snapshot tests: each one pins a specific
 * requirement that a plain `role="dialog"` div silently fails. The
 * `PairingTokenDialog` this replaced had none of them and its docblock
 * claimed Escape worked anyway, so the point of this file is that the
 * claim can no longer be false without turning CI red.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { Dialog, DialogDescription, DialogTitle } from './dialog';

function Harness({ onOpenChange = vi.fn() }: { onOpenChange?: (open: boolean) => void }) {
  return (
    <>
      <button type="button">outside-trigger</button>
      <Dialog open onOpenChange={onOpenChange}>
        <DialogTitle>Confirm branch</DialogTitle>
        <DialogDescription>This cannot be undone.</DialogDescription>
        <button type="button">confirm</button>
        <button type="button">cancel</button>
      </Dialog>
    </>
  );
}

describe('Dialog accessibility contract', () => {
  it('exposes role=dialog with aria-modal so AT treats the page behind as inert', () => {
    render(<Harness />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('wires aria-labelledby and aria-describedby to the generated ids', () => {
    render(<Harness />);
    const dialog = screen.getByRole('dialog');
    const titleId = dialog.getAttribute('aria-labelledby');
    const descId = dialog.getAttribute('aria-describedby');

    expect(titleId).toBeTruthy();
    expect(descId).toBeTruthy();
    // The referenced ids must actually resolve, or the dialog is unlabelled.
    expect(document.getElementById(titleId!)).toHaveTextContent('Confirm branch');
    expect(document.getElementById(descId!)).toHaveTextContent('cannot be undone');
  });

  it('closes on Escape', async () => {
    const onOpenChange = vi.fn();
    render(<Harness onOpenChange={onOpenChange} />);
    await userEvent.keyboard('{Escape}');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('moves focus into the dialog on open', () => {
    render(<Harness />);
    const confirm = screen.getByRole('button', { name: 'confirm' });
    expect(confirm).toHaveFocus();
  });

  it('locks body scroll while open and restores it on unmount', () => {
    const { unmount } = render(<Harness />);
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('restores focus to whatever was focused before the dialog opened', async () => {
    function Stateful() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open-it
          </button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTitle>Peek</DialogTitle>
            <button type="button">inside</button>
          </Dialog>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Stateful />);
    const trigger = screen.getByRole('button', { name: 'open-it' });
    await user.click(trigger);
    expect(screen.getByRole('button', { name: 'inside' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
  });

  it('traps Tab so focus cannot escape to the page behind the overlay', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const confirm = screen.getByRole('button', { name: 'confirm' });
    const cancel = screen.getByRole('button', { name: 'cancel' });

    // The trigger outside the dialog must never be reachable, which is the
    // whole point: it is the element that sits behind the overlay in DOM
    // order, and the document has no focusable element after `cancel`.
    expect(confirm).toHaveFocus();

    await user.tab();
    expect(cancel).toHaveFocus();

    // Tab past the last control wraps to the first instead of escaping.
    await user.tab();
    expect(confirm).toHaveFocus();
    expect(screen.getByRole('button', { name: 'outside-trigger' })).not.toHaveFocus();

    // And Shift+Tab off the first control wraps to the last.
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
  });

  it('does not render anything when closed', () => {
    render(
      <Dialog open={false} onOpenChange={vi.fn()}>
        <DialogTitle>Hidden</DialogTitle>
      </Dialog>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('dismisses on a backdrop click but not on a click inside the content', async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Dialog open onOpenChange={onOpenChange}>
        <DialogTitle>Backdrop</DialogTitle>
        <button type="button">inner</button>
      </Dialog>,
    );
    const dialog = screen.getByRole('dialog');
    await user.click(screen.getByRole('button', { name: 'inner' }));
    expect(onOpenChange).not.toHaveBeenCalled();

    await user.click(dialog.parentElement!);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
