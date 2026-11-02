class FrugalbarLinux < Formula
  desc "AI subscription usage and balances in the Linux Mint Cinnamon tray"
  homepage "https://github.com/seankoji-com/frugalbar-linux"
  url "https://github.com/seankoji-com/frugalbar-linux/archive/refs/tags/v0.1.0.tar.gz"
  # Replaced with the verified release archive SHA before tap publication.
  sha256 "RELEASE_SHA256"
  license "MIT"

  depends_on :linux
  depends_on "gtk+3"
  depends_on "libsecret"
  depends_on "librsvg"
  depends_on "pygobject3"
  depends_on "python@3.15"

  def install
    libexec.install "frugalbar_linux"
    libexec.install "packaging/launch.py"
    (bin/"frugalbar-linux").write <<~SH
      #!/bin/sh
      export PATH="#{HOMEBREW_PREFIX}/bin:#{HOMEBREW_PREFIX}/sbin:$PATH"
      exec "#{Formula["python@3.15"].opt_bin}/python3.15" -I "#{libexec}/launch.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Launch frugalbar-linux inside your Cinnamon desktop session.
      Add it to the application menu with: frugalbar-linux --install-desktop
      Settings can enable login startup and read-only CLI credential discovery.
      Keys saved in Settings use your desktop Secret Service login keyring.
      Tray support targets Cinnamon on X11. If no tray host is available,
      FrugalBar stays usable as a normal window. Do not run it with sudo.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/frugalbar-linux --version")
    result = JSON.parse(shell_output("#{bin}/frugalbar-linux --demo --json"))
    assert_equal true, result["illustrative"]
    assert_equal 10, result["providers"].length
    system Formula["python@3.15"].opt_bin/"python3.15", "-I", "-c", <<~PY
      import gi
      gi.require_version("GdkPixbuf", "2.0")
      from gi.repository import GdkPixbuf
      GdkPixbuf.Pixbuf.new_from_file_at_scale("#{libexec}/frugalbar_linux/assets/openai.svg", 26, 26, True)
    PY
  end
end
