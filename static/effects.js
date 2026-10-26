export class LiveEffects {
  constructor(context) {
    this.context = context;
    this.nodes = [];
    const node = (value) => {
      this.nodes.push(value);
      return value;
    };
    this.input = node(context.createGain());
    this.output = node(context.createGain());
    this.bass = node(context.createBiquadFilter());
    this.bass.type = "lowshelf";
    this.bass.frequency.value = 180;
    this.treble = node(context.createBiquadFilter());
    this.treble.type = "highshelf";
    this.treble.frequency.value = 3500;
    this.highpass = node(context.createBiquadFilter());
    this.highpass.type = "highpass";
    this.lowpass = node(context.createBiquadFilter());
    this.lowpass.type = "lowpass";
    this.shaper = node(context.createWaveShaper());
    this.direct = node(context.createGain());
    this.tremolo = node(context.createGain());
    this.oscillator = node(context.createOscillator());
    this.oscillator.frequency.value = 5;
    this.depth = node(context.createGain());
    this.oscillator.connect(this.depth).connect(this.tremolo.gain);
    this.oscillator.start();
    this.dry = node(context.createGain());
    this.wet = node(context.createGain());
    this.convolver = node(context.createConvolver());
    this.convolver.normalize = false;
    this.input
      .connect(this.bass)
      .connect(this.treble)
      .connect(this.highpass)
      .connect(this.lowpass)
      .connect(this.shaper);
    this.shaper.connect(this.direct).connect(this.tremolo);
    this.delays = [0.18, 0.36].map((time) => {
      const delay = node(context.createDelay(1));
      const gain = node(context.createGain());
      delay.delayTime.value = time;
      this.shaper.connect(delay).connect(gain).connect(this.tremolo);
      return gain;
    });
    this.tremolo.connect(this.dry).connect(this.output);
    this.tremolo.connect(this.convolver).connect(this.wet).connect(this.output);
    this.setParameters({});
  }

  setParameters({
    bass = 0,
    treble = 0,
    effect = "none",
    reverb = 0,
    reverb_room = "hall",
  }) {
    const set = (param, value) =>
      param.setTargetAtTime(value, this.context.currentTime, 0.01);
    set(this.bass.gain, bass);
    set(this.treble.gain, treble);
    set(this.highpass.frequency, effect === "telephone" ? 400 : 10);
    set(
      this.lowpass.frequency,
      ["telephone", "lofi"].includes(effect)
        ? 3400
        : this.context.sampleRate / 2,
    );
    if (this.effect !== effect) {
      this.effect = effect;
      this.shaper.curve = ["distortion", "lofi"].includes(effect)
        ? Float32Array.from({ length: 16385 }, (_, index) => {
            const x = index / 8192 - 1;
            return effect === "distortion"
              ? Math.tanh(x / 0.4) * 0.7
              : Math.round(x * 128) / 128;
          })
        : null;
    }
    set(this.direct.gain, effect === "echo" ? 0.56 : 1);
    this.delays.forEach((gain, i) =>
      set(gain.gain, effect === "echo" ? [0.245, 0.14][i] : 0),
    );
    set(this.depth.gain, effect === "tremolo" ? 0.3 : 0);
    set(this.tremolo.gain, effect === "tremolo" ? 0.7 : 1);
    const duration = reverb_room === "room" ? 0.65 : 1.6;
    if (this.room !== reverb_room) {
      this.room = reverb_room;
      const rate = this.context.sampleRate;
      const impulse = this.context.createBuffer(
        2,
        Math.round(rate * duration),
        rate,
      );
      for (let channel = 0; channel < 2; channel++) {
        const samples = impulse.getChannelData(channel);
        const seed = channel === 0 ? 1 : 101;
        for (let i = 0; i < samples.length; i++) {
          const noise = Math.sin((i + seed) * 12.9898) * 43758.5453;
          samples[i] =
            0.018 *
            Math.sqrt(44100 / rate) *
            (2 * (noise - Math.floor(noise)) - 1) *
            Math.exp((-5 * i) / rate / duration);
        }
      }
      this.convolver.buffer = impulse;
    }
    set(this.dry.gain, 1 - reverb);
    set(this.wet.gain, reverb);
    this.tail = (reverb > 0 ? duration : 0) + (effect === "echo" ? 0.36 : 0);
  }

  disconnect() {
    this.oscillator.stop();
    for (const node of this.nodes) node.disconnect();
  }
}
