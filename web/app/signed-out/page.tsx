export default function SignedOutPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="max-w-md rounded-md border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">Signed out of MBOP</h1>
        <p className="mt-3 text-sm text-slate-600">Your MBOP session has ended. Sign in when you are ready to continue.</p>
        <a href="/" className="mt-6 inline-block rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white">Sign in</a>
      </div>
    </main>
  );
}
