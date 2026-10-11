import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.jetbrains.kotlin.cli.jvm.compiler.EnvironmentConfigFiles;
import org.jetbrains.kotlin.cli.jvm.compiler.KotlinCoreEnvironment;
import org.jetbrains.kotlin.com.intellij.openapi.util.Disposer;
import org.jetbrains.kotlin.com.intellij.psi.PsiElement;
import org.jetbrains.kotlin.com.intellij.psi.PsiErrorElement;
import org.jetbrains.kotlin.com.intellij.psi.util.PsiTreeUtil;
import org.jetbrains.kotlin.config.CompilerConfiguration;
import org.jetbrains.kotlin.psi.*;

public final class KotlinSyntax {
    private static String source;
    private static int[] byteOffsets;
    private static int[] lineNumbers;

    private static String quote(String value) {
        if (value == null) return "null";
        StringBuilder result = new StringBuilder("\"");
        for (char character : value.toCharArray()) {
            switch (character) {
                case '"': result.append("\\\""); break;
                case '\\': result.append("\\\\"); break;
                case '\n': result.append("\\n"); break;
                case '\r': result.append("\\r"); break;
                case '\t': result.append("\\t"); break;
                default:
                    if (character < 32) result.append(String.format("\\u%04x", (int) character));
                    else result.append(character);
            }
        }
        return result.append('"').toString();
    }

    private static String span(PsiElement element) {
        if (element == null) return "null";
        int start = byteOffsets[element.getTextRange().getStartOffset()];
        int end = byteOffsets[element.getTextRange().getEndOffset()];
        return "[" + start + "," + end + "]";
    }

    private static String list(List<String> values) {
        return "[" + String.join(",", values) + "]";
    }

    private static String lambda(KtLambdaExpression expression) {
        List<String> parameters = new ArrayList<>();
        for (KtParameter parameter : expression.getValueParameters()) {
            if (parameter.getDestructuringDeclaration() != null) {
                parameters.add(quote(parameter.getDestructuringDeclaration().getEntries().get(0).getName()));
            } else parameters.add(quote(parameter.getName()));
        }
        return "{\"span\":" + span(expression) + ",\"body\":" + span(expression.getBodyExpression())
            + ",\"parameters\":" + list(parameters) + "}";
    }

    private static String call(KtCallExpression expression) {
        List<String> arguments = new ArrayList<>();
        for (KtValueArgument argument : expression.getValueArguments()) {
            if (argument instanceof KtLambdaArgument) continue;
            String name = argument.getArgumentName() == null ? null : argument.getArgumentName().getAsName().asString();
            arguments.add("{\"name\":" + quote(name) + ",\"span\":" + span(argument)
                + ",\"value\":" + span(argument.getArgumentExpression()) + "}");
        }
        List<String> lambdas = new ArrayList<>();
        for (KtLambdaArgument argument : expression.getLambdaArguments()) {
            if (argument.getLambdaExpression() != null) lambdas.add(lambda(argument.getLambdaExpression()));
        }
        List<String> namedLambdas = new ArrayList<>();
        for (KtValueArgument argument : expression.getValueArguments()) {
            if (argument.getArgumentName() != null && argument.getArgumentExpression() instanceof KtLambdaExpression) {
                namedLambdas.add("{\"name\":" + quote(argument.getArgumentName().getAsName().asString())
                    + ",\"lambda\":" + lambda((KtLambdaExpression) argument.getArgumentExpression()) + "}");
            }
        }
        PsiElement full = expression;
        if (expression.getParent() instanceof KtQualifiedExpression
            && ((KtQualifiedExpression) expression.getParent()).getSelectorExpression() == expression) full = expression.getParent();
        KtNamedFunction function = PsiTreeUtil.getParentOfType(expression, KtNamedFunction.class);
        return "{\"span\":" + span(expression) + ",\"full\":" + span(full)
            + ",\"callee\":" + quote(expression.getCalleeExpression() == null ? "" : expression.getCalleeExpression().getText())
            + ",\"arguments\":" + list(arguments) + ",\"arguments_span\":" + span(expression.getValueArgumentList())
            + ",\"lambdas\":" + list(lambdas) + ",\"named_lambdas\":" + list(namedLambdas) + ",\"function\":" + span(function)
            + ",\"line\":" + lineNumbers[expression.getTextOffset()] + "}";
    }

    public static void main(String[] arguments) throws Exception {
        var disposable = Disposer.newDisposable();
        try {
            var environment = KotlinCoreEnvironment.createForProduction(
                disposable, new CompilerConfiguration(), EnvironmentConfigFiles.JVM_CONFIG_FILES);
            var factory = new KtPsiFactory(environment.getProject(), false);
            for (String filename : Files.readAllLines(Path.of(arguments[0]))) {
                source = Files.readString(Path.of(filename)).replace("\r\n", "\n");
                byteOffsets = new int[source.length() + 1];
                lineNumbers = new int[source.length() + 1];
                int byteOffset = 0;
                int lineNumber = 1;
                for (int position = 0; position < source.length();) {
                    int point = source.codePointAt(position);
                    int width = Character.charCount(point);
                    for (int part = 0; part < width; part++) {
                        byteOffsets[position + part] = byteOffset;
                        lineNumbers[position + part] = lineNumber;
                    }
                    byteOffset += new String(Character.toChars(point)).getBytes(StandardCharsets.UTF_8).length;
                    if (point == '\n') lineNumber++;
                    position += width;
                }
                byteOffsets[source.length()] = byteOffset;
                lineNumbers[source.length()] = lineNumber;
                KtFile file = factory.createFile(Path.of(filename).getFileName().toString(), source);
                List<String> imports = new ArrayList<>();
                for (KtImportDirective directive : file.getImportDirectives()) {
                    imports.add("{\"name\":" + quote(directive.getImportedFqName() == null ? "" : directive.getImportedFqName().asString())
                        + ",\"alias\":" + quote(directive.getAliasName()) + ",\"star\":" + directive.isAllUnder() + "}");
                }
                List<String> errors = new ArrayList<>();
                for (PsiErrorElement error : PsiTreeUtil.findChildrenOfType(file, PsiErrorElement.class)) {
                    errors.add("{\"span\":" + span(error) + ",\"message\":" + quote(error.getErrorDescription()) + "}");
                }
                List<String> functions = new ArrayList<>();
                for (KtNamedFunction function : PsiTreeUtil.findChildrenOfType(file, KtNamedFunction.class)) {
                    List<String> parameters = new ArrayList<>();
                    for (KtParameter parameter : function.getValueParameters()) {
                        parameters.add("{\"name\":" + quote(parameter.getName()) + ",\"type\":"
                            + quote(parameter.getTypeReference() == null ? "" : parameter.getTypeReference().getText()) + "}");
                    }
                    boolean composable = function.getAnnotationEntries().stream().anyMatch(
                        annotation -> annotation.getShortName() != null && annotation.getShortName().asString().equals("Composable"));
                    functions.add("{\"name\":" + quote(function.getName()) + ",\"span\":" + span(function)
                        + ",\"body\":" + span(function.getBodyExpression()) + ",\"composable\":" + composable
                        + ",\"parameters\":" + list(parameters) + "}");
                }
                List<String> calls = new ArrayList<>();
                for (KtCallExpression expression : PsiTreeUtil.findChildrenOfType(file, KtCallExpression.class)) calls.add(call(expression));
                List<String> loops = new ArrayList<>();
                for (KtForExpression loop : PsiTreeUtil.findChildrenOfType(file, KtForExpression.class)) {
                    KtParameter parameter = loop.getLoopParameter();
                    String name = parameter == null ? null : parameter.getName();
                    if (loop.getDestructuringDeclaration() != null) {
                        name = loop.getDestructuringDeclaration().getEntries().get(0).getName();
                    }
                    loops.add("{\"span\":" + span(loop) + ",\"body\":" + span(loop.getBody())
                        + ",\"parameter\":" + quote(name) + "}");
                }
                System.out.println("{\"path\":" + quote(filename) + ",\"package\":" + quote(file.getPackageFqName().asString())
                    + ",\"imports\":" + list(imports) + ",\"functions\":" + list(functions)
                    + ",\"calls\":" + list(calls) + ",\"loops\":" + list(loops) + ",\"errors\":" + list(errors) + "}");
            }
        } finally {
            Disposer.dispose(disposable);
        }
    }
}
