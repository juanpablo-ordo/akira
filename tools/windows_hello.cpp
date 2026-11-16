#include <windows.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Security.Credentials.UI.h>
#include <UserConsentVerifierInterop.h>

extern "C" __declspec(dllexport) int WINAPI AkiraVerifyIdentity(HWND owner) noexcept {
    DWORD process = 0;
    GetWindowThreadProcessId(owner, &process);
    if (process != GetCurrentProcessId()) return 0;
    try {
        winrt::init_apartment(winrt::apartment_type::multi_threaded);
        struct Apartment {
            ~Apartment() { winrt::uninit_apartment(); }
        } apartment;
        using namespace winrt::Windows::Security::Credentials::UI;
        using Verification = winrt::Windows::Foundation::IAsyncOperation<UserConsentVerificationResult>;
        auto verifier = winrt::get_activation_factory<UserConsentVerifier, IUserConsentVerifierInterop>();
        Verification operation{nullptr};
        auto prompt = winrt::hstring(L"Restablecer el PIN de privacidad de AKIRA");
        winrt::check_hresult(verifier->RequestVerificationForWindowAsync(
            owner, winrt::get_abi(prompt), winrt::guid_of<Verification>(), winrt::put_abi(operation)));
        return operation.get() == UserConsentVerificationResult::Verified ? 1 : 0;
    } catch (...) {
        return 0;
    }
}
